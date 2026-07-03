"""
clinicaltrials.py
-----------------
This file has ONE job: given a search word (like "semaglutide"), go out to
ClinicalTrials.gov, ask for some trials, and hand back a clean list of them.

It knows NOTHING about AI, scoring, or databases. One job only.

DESIGN CHOICE — fail honestly:
If the live fetch fails, we RAISE A CLEAR ERROR rather than return stand-in
data. For a medical tool, returning wrong-but-plausible data silently is worse
than returning nothing. The caller (our app) will catch this and show the user
an honest "couldn't reach the database, try again" message.

We use urllib (Python's BUILT-IN web tool) instead of httpx because on some
networks ClinicalTrials.gov rejects httpx's default request signature with a
403, while accepting urllib and normal browsers.
"""

import json                    # to turn the API's JSON text into Python objects
import urllib.request          # Python's built-in tool for making web requests
import urllib.parse            # to safely build the query string in the URL
import urllib.error            # the specific error urllib raises on HTTP 
import sys


BASE_URL = "https://clinicaltrials.gov/api/v2/studies"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) cheiron-demo/1.0"


# A custom error type so the rest of the app can recognize "the fetch failed"
# specifically, and handle it cleanly. (Defining your own error is a normal,
# useful pattern — it makes failures easy to catch by name.)
class TrialsFetchError(Exception):
    pass


def fetch_trials(query: str, limit: int = 8) -> list[dict]:
    """
    Ask ClinicalTrials.gov for trials matching `query`, return up to `limit`
    of them as a clean list of dictionaries.

    Raises TrialsFetchError if the live service can't be reached or returns
    bad data — we never substitute unrelated data.
    """

    params = urllib.parse.urlencode({
        "query.term": query,
        "pageSize": limit,
        "sort": "LastUpdatePostDate:desc",
    })
    full_url = f"{BASE_URL}?{params}"

    # Try the live API. If anything goes wrong, convert it into our own clear
    # error instead of returning fake data. 'raise ... from error' keeps the
    # original cause attached, which helps with debugging.
    try:
        request = urllib.request.Request(full_url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
            data = json.loads(raw)
    except Exception as error:
        raise TrialsFetchError(
            f"Could not reach ClinicalTrials.gov for query '{query}': {error}"
        ) from error

    # Clean up the messy JSON into our simple, agreed-upon shape.
    trials = []
    for study in data.get("studies", []):
        protocol = study.get("protocolSection", {})

        identification = protocol.get("identificationModule", {})
        status = protocol.get("statusModule", {})
        design = protocol.get("designModule", {})
        conditions = protocol.get("conditionsModule", {})
        arms = protocol.get("armsInterventionsModule", {})
        description = protocol.get("descriptionModule", {})

        nct_id = identification.get("nctId", "")

        trial = {
            "nct_id": nct_id,
            "title": identification.get("briefTitle", ""),
            "status": status.get("overallStatus", ""),
            "phases": design.get("phases", []),
            "conditions": conditions.get("conditions", []),
            "interventions": [
                item.get("name", "")
                for item in arms.get("interventions", [])
            ],
            "summary": (description.get("briefSummary", "") or "")[:500],
            "url": f"https://clinicaltrials.gov/study/{nct_id}" if nct_id else "",
        }
        trials.append(trial)

    return trials


# Runs only when you execute THIS file directly (python clinicaltrials.py).
if __name__ == "__main__":

    # Two ways to get a drug name dynamically:
    #
    # 1. Command-line argument: `python clinicaltrials.py aspirin`
    #    sys.argv is a list of what you typed. sys.argv[0] is the filename,
    #    sys.argv[1] (if present) is the first thing after it — the drug.
    #
    # 2. If you didn't pass one, ask interactively with input().
    if len(sys.argv) > 1:
        # Join in case the drug is multiple words, e.g. "heart failure".
        query = " ".join(sys.argv[1:])
    else:
        query = input("Enter a drug or condition to search: ").strip()

    # Guard against an empty search — fail early with a clear message.
    if not query:
        print("No search term entered. Try again.")
        sys.exit(1)

    print(f"\nSearching for: {query}\n")

    # We know fetch_trials can raise TrialsFetchError now (we made it honest).
    # So we catch it here and show a friendly message instead of an ugly crash.
    try:
        results = fetch_trials(query)
    except TrialsFetchError as error:
        print(f"Couldn't fetch trials: {error}")
        sys.exit(1)

    print(f"Got {len(results)} trials.\n")
    for t in results:
        print(f"- {t['nct_id']}: {t['title']}")
        print(f"    status: {t['status']} | phases: {t['phases']}")
        print()