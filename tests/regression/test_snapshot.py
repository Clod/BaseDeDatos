"""
test_snapshot.py — The golden comparison: full pipeline output vs. blessed state.

PASS    -> the ETL produced byte-identical canonical output to the last
           blessed golden snapshot.
FAIL    -> behavior changed. Read the diff: it is either a regression (fix
           the code) or an intentional change (review it, then re-bless with
           `--bless`). See README.md §5 "Interpreting a failure".
"""

from __future__ import annotations

import pytest

from . import snapshot_lib

pytestmark = pytest.mark.regression


def test_pipeline_output_matches_golden(pipeline_state, request: pytest.FixtureRequest) -> None:
    if request.config.getoption("--bless"):
        snapshot_lib.write_golden(pipeline_state.dump_run1)
        total_rows = sum(len(v) for v in pipeline_state.dump_run1.values())
        pytest.skip(
            f"BLESSED: wrote new golden snapshot ({total_rows} rows across "
            f"{sum(1 for v in pipeline_state.dump_run1.values() if v)} non-empty tables, "
            f"{pipeline_state.n_cases} corpus cases, {pipeline_state.passes} pipeline passes). "
            "Review `git diff tests/regression/golden/` before committing."
        )

    golden = snapshot_lib.load_golden()
    if not any(golden.values()):
        pytest.fail(
            "No golden snapshot exists yet. Generate the initial baseline with:\n"
            "  pytest tests/regression --run-regression --bless\n"
            "then audit it (prompts/blessing_audit.md) before trusting it."
        )

    diff = snapshot_lib.diff_states(golden, pipeline_state.dump_run1)
    assert diff == "", (
        "Pipeline output diverged from the golden snapshot.\n"
        "Regression OR intentional change — review the diff below; if the new "
        "behavior is correct, re-bless with --bless and commit the golden diff.\n\n"
        + diff
    )


def test_every_routed_corpus_case_reached_a_terminal_state(pipeline_state) -> None:
    """No routed corpus event may be left at is_processed = 0 unless it is a
    documented expected-orphan child (parent missing from production too)."""
    from . import harness

    expected_orphans = {
        case["id"] for case in harness.read_corpus_cases()
        if case.get("meta", {}).get("expected_orphan")
    }
    negatives = {
        case["id"] for case in harness.read_corpus_cases()
        if case.get("meta", {}).get("role") == "negative"
    }

    import json

    stuck = []
    for line in pipeline_state.dump_run1["SentianceEventos"]:
        row = json.loads(line)
        if row["is_processed"] in (0, False) and row["id"] not in expected_orphans | negatives:
            stuck.append((row["id"], row["tipo"]))
    assert stuck == [], f"Routed corpus events left unprocessed: {stuck}"
