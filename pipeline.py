"""
pipeline.py
-----------
The verified-brief pipeline with retry loop.

- Level 1 (fast, free) always runs.
- Level 2 (Gemini) runs only if run_level2=True (protects quota; on-demand).
- If Level 2 is requested but Gemini is UNAVAILABLE, we report that honestly —
  we never claim the brief passed a check that didn't actually run.
- demo_flaw injects a flaw into the first attempt to showcase the loop.
"""

from ai import write_brief
from scoring import score_citations
from judge import judge_brief, JudgeUnavailable

MAX_RETRIES = 2


def _inject_flaw(brief, trials, flaw_type):
    if flaw_type == "fake_id":
        return brief + "\n\nAdditionally, a landmark trial confirmed universal efficacy [NCT99999999]."
    if flaw_type == "unsupported" and trials:
        rid = trials[0]["nct_id"]
        return brief + (f"\n\nNotably, {rid} demonstrated complete remission of disease in "
                        f"100% of participants with no adverse events [{rid}].")
    return brief


def generate_verified_brief(query, trials, run_level2=False, demo_flaw=""):
    retries_used = 0
    retry_log = []
    feedback = ""
    first_attempt = True
    level2_status = "not_run"        # "not_run" | "passed" | "unavailable"
    judge_results = None

    while True:
        attempt_number = retries_used + 1
        brief = write_brief(query, trials, feedback=feedback)

        if first_attempt and demo_flaw:
            brief = _inject_flaw(brief, trials, demo_flaw)
        first_attempt = False

        # --- Level 1 (always) ---
        score = score_citations(brief, trials)
        if score["invalid_ids"]:
            if retries_used < MAX_RETRIES:
                retries_used += 1
                retry_log.append({"attempt": attempt_number, "step": "Level 1",
                                  "reason": f"fabricated citation(s): {', '.join(score['invalid_ids'])}"})
                real_ids = [t["nct_id"] for t in trials]
                feedback = (f"You cited NCT ids not in the provided trials: "
                            f"{', '.join(score['invalid_ids'])}. Only cite from: {', '.join(real_ids)}.")
                continue
            else:
                return _result(brief, score, judge_results, "not_run", attempt_number,
                               retry_log, False, "Some citations remained invalid after retries.")

        # --- Level 2 (only if requested) ---
        if run_level2:
            try:
                judge_results = judge_brief(brief, trials)
                unsupported = [j for j in judge_results
                               if j.get("verdict") in ("NOT_SUPPORTED", "PARTIAL")]
                if unsupported:
                    if retries_used < MAX_RETRIES:
                        retries_used += 1
                        bad = ', '.join(j["nct_id"] for j in unsupported)
                        retry_log.append({"attempt": attempt_number, "step": "Level 2",
                                          "reason": f"unsupported claim(s) for: {bad}"})
                        feedback = (f"An independent reviewer found claims about these trials "
                                    f"NOT supported by the data: {bad}. Revise or remove them.")
                        continue
                    else:
                        return _result(brief, score, judge_results, "failed", attempt_number,
                                       retry_log, False, "Some claims unverified after retries.")
                level2_status = "passed"
            except JudgeUnavailable as e:
                # HONEST: the judge couldn't run. Do NOT claim it passed.
                level2_status = "unavailable"
                return _result(brief, score, None, "unavailable", attempt_number,
                               retry_log, True,
                               "Level 1 passed. Level 2 (independent judge) was unavailable "
                               f"— not verified. ({e})")

        return _result(brief, score, judge_results, level2_status, attempt_number,
                       retry_log, True, "")


def _result(brief, score, judge_results, level2_status, attempts, retry_log, passed, note):
    return {
        "brief_markdown": brief, "score": score, "judge_results": judge_results,
        "level2_status": level2_status, "attempts": attempts, "retry_log": retry_log,
        "passed": passed, "note": note,
    }


if __name__ == "__main__":
    from clinicaltrials import fetch_trials
    trials = fetch_trials("semaglutide")
    print("--- Level 1 only (fast) ---")
    r = generate_verified_brief("semaglutide", trials, run_level2=False)
    print(f"Attempts {r['attempts']} | Passed {r['passed']} | L2 {r['level2_status']}")