"""test_reprocess.py — Reprocessing DrivingInsights rows must not duplicate them.

The ETL's re-entry contract is the is_processed flag, but operators sometimes
reset rows to 0 to reprocess a window with fixed code. Before the idempotency
fix, DrivingInsightsTrip was a bare INSERT and the five child safety-event
tables inserted unconditionally, so a reprocess doubled the parent trip and its
children — inflating the harsh-event counts the Movilidad bridge derives from
them. This test drives that exact path: reset every DrivingInsights* row to
pending, reprocess to completion, and assert the subtree did not grow.

This test MUTATES the live post-pipeline DB (it also re-inserts upstream
SdkSourceEvent rows, which are out of scope here), so it depends on
`pipeline_state` to run after the canonical cycle and is named to sort after
the live-DB invariant/ordering tests. The frozen snapshot tests are unaffected.
"""

from __future__ import annotations

import pytest

from . import harness

pytestmark = pytest.mark.regression

DI_TABLES = [
    "DrivingInsightsTrip",
    "DrivingInsightsHarshEvent",
    "DrivingInsightsPhoneEvent",
    "DrivingInsightsCallEvent",
    "DrivingInsightsSpeedingEvent",
    "DrivingInsightsWrongWayDrivingEvent",
]


def _counts(cur) -> dict[str, int]:
    out: dict[str, int] = {}
    for t in DI_TABLES:
        cur.execute(f"SELECT COUNT(*) FROM {t}")
        out[t] = cur.fetchone()[0]
    return out


def test_reprocess_does_not_duplicate_driving_insights(local_db, pipeline_state) -> None:
    with harness.connect(local_db) as conn:
        before = _counts(conn.cursor())

    # Reset every DrivingInsights* landing-zone row back to pending, then reprocess.
    with harness.connect(local_db) as conn:
        cur = conn.cursor()
        cur.execute("UPDATE SentianceEventos SET is_processed = 0 WHERE tipo LIKE 'DrivingInsights%'")
        conn.commit()

    harness.run_pipeline_to_completion(local_db)

    with harness.connect(local_db) as conn:
        cur = conn.cursor()
        after = _counts(cur)
        cur.execute(
            "SELECT COUNT(*) FROM ("
            "  SELECT canonical_transport_event_id, sentiance_user_id"
            "  FROM DrivingInsightsTrip"
            "  GROUP BY canonical_transport_event_id, sentiance_user_id"
            "  HAVING COUNT(*) > 1) d"
        )
        dup_parents = cur.fetchone()[0]

    assert after == before, (
        "Reprocessing DrivingInsights duplicated rows — the subtree is not idempotent:\n"
        + "\n".join(f"  {t}: {before[t]} -> {after[t]}" for t in DI_TABLES if before[t] != after[t])
    )
    assert dup_parents == 0, (
        f"{dup_parents} (canonical_transport_event_id, sentiance_user_id) pair(s) "
        "have more than one DrivingInsightsTrip after reprocess"
    )
