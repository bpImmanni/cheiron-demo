"""
test_scoring.py
---------------
Automated tests for the Level 1 citation scorer — the core verification logic.

These are pure and deterministic (no API calls), so they run fast and reliably
in CI. They prove the thing the whole app claims: fabricated citations get caught.

Run locally with:  pytest
"""

from scoring import score_citations


# A small set of fake "trials" — just needs nct_id, which is what the scorer checks.
FAKE_TRIALS = [
    {"nct_id": "NCT00000001"},
    {"nct_id": "NCT00000002"},
    {"nct_id": "NCT00000003"},
]


def test_all_valid_citations():
    """A brief citing only real ids should score 100% with no invalids."""
    brief = "Finding A [NCT00000001]. Finding B [NCT00000002]."
    result = score_citations(brief, FAKE_TRIALS)
    assert result["invalid_ids"] == []
    assert result["accuracy_percent"] == 100.0


def test_catches_fabricated_citation():
    """THE KEY TEST: a fabricated id must be caught as invalid."""
    brief = "Real finding [NCT00000001]. Made-up finding [NCT99999999]."
    result = score_citations(brief, FAKE_TRIALS)
    # The fake id must be flagged.
    assert "NCT99999999" in result["invalid_ids"]
    # The real id must NOT be flagged.
    assert "NCT00000001" in result["valid_ids"]
    # Accuracy must drop below 100%.
    assert result["accuracy_percent"] < 100.0


def test_weighted_penalty():
    """Fabricated citations are penalized heavily (our -5 weighting)."""
    brief = "One real [NCT00000001]. One fake [NCT99999999]."
    result = score_citations(brief, FAKE_TRIALS)
    # 1 valid (+1) + 1 invalid (-5) = -4
    assert result["points"] == -4


def test_no_citations():
    """A brief with no citations shouldn't crash (divide-by-zero guard)."""
    brief = "This brief has no citations at all."
    result = score_citations(brief, FAKE_TRIALS)
    assert result["total_citations"] == 0
    assert result["accuracy_percent"] == 0.0