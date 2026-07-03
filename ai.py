"""
ai.py
-----
Takes trials and asks Claude to write a SHORT, CITED brief using ONLY those
trials. Also handles conversational follow-up questions. Trials in -> text out.

The "grounding" happens here: we paste the real trial data into the prompt and
instruct Claude to answer only from it (the core of RAG). Claude has no memory
of its own — for conversation, the caller passes prior turns and we re-send them.
"""

import json
from dotenv import load_dotenv
from anthropic import Anthropic

# Load .env so ANTHROPIC_API_KEY is available, then create the client (it reads
# the key from the environment automatically — we never write the key here).
load_dotenv()
client = Anthropic()

MODEL = "claude-sonnet-4-5"

# System prompt for the BRIEF. This is where we control grounding/hallucination.
SYSTEM_PROMPT = """You are a clinical research analyst writing concise decision \
briefs for biopharma teams.

STRICT RULES:
- Use ONLY the trial data provided in the user's message. Do not use outside \
knowledge or invent anything.
- After every factual claim, cite the trial(s) it comes from using the NCT id \
in square brackets, e.g. [NCT03548935].
- If the provided trials do not cover something, say so plainly instead of guessing.

Write clean Markdown with these sections:
## Snapshot   (2-3 sentences on the overall state of trials for this query)
## Landscape  (bulleted: key interventions, phases, sponsors, status)
## Notable trials  (3-5 bullets, each citing its NCT id)
## Gaps       (what the provided data does NOT tell us)

Keep the whole brief under ~300 words."""

# System prompt for follow-up Q&A — same grounding discipline, conversational.
QA_SYSTEM_PROMPT = """You are a clinical research analyst answering follow-up \
questions from a biopharma team about a specific set of clinical trials.

STRICT RULES (same as before):
- Use ONLY the trial data provided. Do NOT use outside knowledge or invent anything.
- Cite every factual claim with the trial's NCT id in square brackets, e.g. [NCT03548935].
- If the trials do not contain the answer, say so plainly. Never guess or fill \
gaps from memory. It is correct and good to say "the provided trials don't cover that."
- You may reference earlier answers in this conversation, but every factual claim \
must still trace to the trial data.

Keep answers concise and directly responsive to the question."""


def write_brief(query: str, trials: list[dict], feedback: str = "") -> str:
    """
    Ask Claude to write a grounded, cited brief for `query` using `trials`.
    If `feedback` is given (during a retry), it tells Claude what to fix.
    Returns the brief as a Markdown string.
    """
    trials_text = json.dumps(trials, indent=2)

    user_message = (
        f"Query: {query}\n\n"
        f"Here are {len(trials)} clinical trials to base the brief on:\n\n"
        f"{trials_text}\n\n"
        f"Write the decision brief now, grounded only in these trials."
    )

    # On a retry, append the specific problems to fix. This makes the retry a
    # targeted CORRECTION, not a blind reroll.
    if feedback:
        user_message += (
            f"\n\nIMPORTANT — your previous attempt had these problems. "
            f"Fix them in this version:\n{feedback}"
        )

    response = client.messages.create(
        model=MODEL,
        max_tokens=1200,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )
    return response.content[0].text


def answer_question(question: str, trials: list[dict], history: list[dict]) -> str:
    """
    Answer a follow-up `question` grounded in `trials`, aware of prior `history`.

    - question: the user's new question
    - trials: the trials the brief was based on (grounding)
    - history: prior turns as [{"role": "user"/"assistant", "content": "..."}]
    Returns the answer text. Re-sending history each call is what creates memory.
    """
    trials_text = json.dumps(trials, indent=2)

    messages = []
    # Hand over the trials once, as an opening exchange, so they're "in" the chat.
    messages.append({
        "role": "user",
        "content": f"Here are the clinical trials for this session:\n\n{trials_text}\n\n"
                   f"I'll ask questions about these. Answer only from this data.",
    })
    messages.append({
        "role": "assistant",
        "content": "Understood. I'll answer only from these trials and cite each claim.",
    })
    # Replay prior turns (the memory), then add the new question.
    for turn in history:
        messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append({"role": "user", "content": question})

    response = client.messages.create(
        model=MODEL,
        max_tokens=1000,
        system=QA_SYSTEM_PROMPT,
        messages=messages,
    )
    return response.content[0].text


# --- Isolated test (runs only with: python ai.py) ---------------------------
if __name__ == "__main__":
    from clinicaltrials import fetch_trials, TrialsFetchError

    query = "semaglutide"
    print(f"Fetching trials for: {query} ...\n")
    try:
        trials = fetch_trials(query)
    except TrialsFetchError as error:
        print(f"Couldn't fetch trials: {error}")
        raise SystemExit(1)

    # Test 1: the brief.
    print("--- Testing write_brief ---")
    brief = write_brief(query, trials)
    print(brief)

    # Test 2: conversational memory (Q2 depends on Q1).
    print("\n--- Testing conversational memory ---")
    history = []
    q1 = "Which of these trials are the most advanced (latest phase)?"
    a1 = answer_question(q1, trials, history)
    print("Q1:", q1, "\nA1:", a1, "\n")
    history += [{"role": "user", "content": q1}, {"role": "assistant", "content": a1}]

    q2 = "Of those, which is recruiting?"
    a2 = answer_question(q2, trials, history)
    print("Q2:", q2, "\nA2:", a2)