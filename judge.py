"""
judge.py
--------
LEVEL 2 check: use Gemini (a DIFFERENT provider) as an independent judge of
whether the brief's claims are supported by the cited trials.

If Gemini is UNAVAILABLE (rate limit, outage), we do NOT pretend the brief
passed — we raise JudgeUnavailable so the caller can report it honestly.
"""

import os
import json
import time

from dotenv import load_dotenv
from google import genai

load_dotenv()
client = genai.Client()
JUDGE_MODEL = "gemini-2.5-flash"


class JudgeUnavailable(Exception):
    """Raised when the judge (Gemini) can't be reached — so we never silently pass."""
    pass


def judge_citation(claim_context: str, trial: dict, max_retries: int = 3) -> dict:
    trial_text = json.dumps(trial, indent=2)
    prompt = (
        "You are an impartial fact-checker for clinical trial citations.\n\n"
        "A brief made claims and cited the trial below. Decide whether the "
        "trial's data SUPPORTS the way it is cited.\n\n"
        f"--- BRIEF EXCERPT ---\n{claim_context}\n\n"
        f"--- ACTUAL TRIAL DATA ---\n{trial_text}\n\n"
        "Respond with ONLY a JSON object, no other text, in exactly this shape:\n"
        '{"verdict": "SUPPORTED" or "NOT_SUPPORTED" or "PARTIAL", '
        '"reason": "one short sentence"}'
    )

    last_error = None
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(model=JUDGE_MODEL, contents=prompt)
            raw = response.text.strip()
            if raw.startswith("```"):
                raw = raw.strip("`")
                raw = raw[raw.find("{"):raw.rfind("}") + 1]
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return {"verdict": "UNKNOWN", "reason": f"Unparseable judge reply: {raw[:100]}"}
        except Exception as error:
            last_error = error
            time.sleep(2 ** attempt)   # 1s, 2s, 4s

    # All retries failed — signal unavailability, do NOT fake a verdict.
    raise JudgeUnavailable(str(last_error)[:200])


def judge_brief(brief_text: str, trials: list[dict]) -> list[dict]:
    """
    Judge each cited trial. Raises JudgeUnavailable if the judge can't be
    reached — the caller must handle that (never silently pass).
    """
    import re
    cited_ids = set(re.findall(r"NCT\d{8}", brief_text))
    trials_by_id = {t["nct_id"]: t for t in trials}

    results = []
    for nct_id in sorted(cited_ids):
        trial = trials_by_id.get(nct_id)
        if trial is None:
            results.append({"nct_id": nct_id, "verdict": "NOT_IN_DATA",
                            "reason": "Cited id was not in the retrieved trials."})
            continue
        verdict = judge_citation(brief_text, trial)   # may raise JudgeUnavailable
        verdict["nct_id"] = nct_id
        results.append(verdict)
        time.sleep(4)   # be polite to the free-tier rate limit
    return results


if __name__ == "__main__":
    from clinicaltrials import fetch_trials
    from ai import write_brief
    trials = fetch_trials("semaglutide")
    brief = write_brief("semaglutide", trials)
    try:
        for v in judge_brief(brief, trials):
            print(f"{v['nct_id']}: {v['verdict']} — {v.get('reason','')}")
    except JudgeUnavailable as e:
        print(f"Judge unavailable: {e}")