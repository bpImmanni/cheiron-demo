"""
scoring.py
----------
This file has ONE job: given a brief (text) and the trials it was supposed to
be based on, check whether the citations in the brief are REAL.

No AI inside — pure, deterministic Python. Same input -> same score, always.
That's the point: the score is trustworthy because nothing is guessing.
"""

import re    # Python's built-in regular-expression (text-pattern) tool


# The pattern for a citation: the letters "NCT" followed by exactly 8 digits.
#   \d   = any digit (0-9)
#   {8}  = exactly eight of them
# re.compile builds the pattern once so it's efficient to reuse.
NCT_PATTERN = re.compile(r"NCT\d{8}")

# Scoring weights (our design decision):
POINTS_PER_VALID = 1     # a real citation is worth +1
POINTS_PER_INVALID = -5  # a fabricated citation costs -5 (medicine: fakes are dangerous)


def score_citations(brief_text: str, trials: list[dict]) -> dict:
    """
    Extract every NCT id cited in `brief_text`, check each against the real
    ids in `trials`, and return a score breakdown.
    """

    # 1. EXTRACT: find every "NCT########" in the brief.
    #    findall returns a list of all matches. We use a set to dedupe —
    #    citing the same trial 3 times shouldn't count as 3 separate checks.
    cited_ids = set(NCT_PATTERN.findall(brief_text))

    # 2. BUILD THE TRUTH: the set of ids that were ACTUALLY in our trials.
    real_ids = {trial["nct_id"] for trial in trials}

    # 3. COMPARE: split cited ids into valid (real) and invalid (not real).
    valid_ids = sorted(cited_ids & real_ids)      # in both = valid
    invalid_ids = sorted(cited_ids - real_ids)    # cited but not real = invalid

    total = len(cited_ids)

    # 4. SCORE:
    #    - percent valid: intuitive "how many citations were real"
    #    - weighted points: rewards valid, punishes invalid heavily
    accuracy_percent = round(100 * len(valid_ids) / total, 1) if total else 0.0
    points = len(valid_ids) * POINTS_PER_VALID + len(invalid_ids) * POINTS_PER_INVALID

    return {
        "accuracy_percent": accuracy_percent,
        "points": points,
        "total_citations": total,
        "valid_ids": valid_ids,
        "invalid_ids": invalid_ids,
    }


# Isolated test: fetch trials, write a brief, score its citations, print it all.
if __name__ == "__main__":
    from clinicaltrials import fetch_trials, TrialsFetchError
    from ai import write_brief

    query = "semaglutide"
    print(f"Fetching trials for: {query} ...")
    try:
        trials = fetch_trials(query)
    except TrialsFetchError as error:
        print(f"Couldn't fetch trials: {error}")
        raise SystemExit(1)

    print("Writing brief...")
    brief = write_brief(query, trials)

    print("Scoring citations...\n")
    score = score_citations(brief, trials)

    print("=" * 50)
    print(f"Citations found:   {score['total_citations']}")
    print(f"Valid:             {len(score['valid_ids'])}  {score['valid_ids']}")
    print(f"Invalid:           {len(score['invalid_ids'])}  {score['invalid_ids']}")
    print(f"Accuracy:          {score['accuracy_percent']}%")
    print(f"Weighted points:   {score['points']}")
    print("=" * 50)