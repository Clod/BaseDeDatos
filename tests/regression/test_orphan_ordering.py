"""
test_orphan_ordering.py — Child events arriving before their parent must wait.

Takes a real parent/child pair from the corpus and replays it out of order
under a fresh transport id (the id is re-suffixed so the pair does not collide
with the trips already created by the main pipeline run — the payloads remain
real production data, only the correlation key changes):

    1. Insert ONLY the child  -> run ETL  -> child must stay is_processed = 0,
       no SdkSourceEvent, no child-table row (orphan guard).
    2. Insert the parent      -> run ETL  -> parent processes, then the
       retried child processes, and the child-table row exists.

This test runs strictly after pipeline_state is frozen, so the extra rows it
inserts can never leak into the snapshot or idempotency comparisons.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from . import harness

pytestmark = pytest.mark.regression

CHILD_TABLE_BY_TIPO = {
    "DrivingInsightsHarshEvents": "DrivingInsightsHarshEvent",
    "DrivingInsightsPhoneEvents": "DrivingInsightsPhoneEvent",
    "DrivingInsightsCallEvents": "DrivingInsightsCallEvent",
    "DrivingInsightsSpeedingEvents": "DrivingInsightsSpeedingEvent",
    "DrivingInsightsWrongWayDrivingEvents": "DrivingInsightsWrongWayDrivingEvent",
}

CHILD_CASE_ID = 90_000_001
PARENT_CASE_ID = 90_000_002


def _find_real_pair() -> tuple[dict[str, Any], dict[str, Any], str] | None:
    """Returns (child_case, parent_case, transport_id) from the corpus, or None."""
    cases = harness.read_corpus_cases()
    parents_by_tid = {}
    for case in cases:
        if case["tipo"].lower() == "drivinginsights":
            payload = json.loads(case["json"])
            tid = (payload.get("transportEvent") or {}).get("id")
            if tid:
                parents_by_tid[(tid, case.get("sentianceid"))] = case
    for case in cases:
        if case["tipo"] in CHILD_TABLE_BY_TIPO and not case.get("meta", {}).get("expected_orphan"):
            tid = json.loads(case["json"]).get("transportId")
            parent = parents_by_tid.get((tid, case.get("sentianceid")))
            if parent is not None:
                return case, parent, tid
    return None


def _requeued(case: dict[str, Any], new_id: int, old_tid: str, new_tid: str) -> dict[str, Any]:
    return {
        "id": new_id,
        "sentianceid": case.get("sentianceid"),
        "tipo": case["tipo"],
        "json": case["json"].replace(old_tid, new_tid),
        "meta": {},
    }


def _scalar(cursor: Any, sql: str, *params: Any) -> Any:
    row = cursor.execute(sql, params).fetchone()
    return row[0] if row else None


def test_child_before_parent_waits_then_completes(local_db, pipeline_state) -> None:
    pair = _find_real_pair()
    if pair is None:
        pytest.skip("corpus has no child event with its parent — top up the corpus first")
    child, parent, tid = pair
    new_tid = tid[:-4] + ("0000" if tid[-4:] != "0000" else "1111")
    assert len(new_tid) == len(tid)

    # Step 1: child arrives alone -> orphan guard must park it.
    harness.load_corpus_cases([_requeued(child, CHILD_CASE_ID, tid, new_tid)], local_db)
    harness.make_etl(local_db).run(batch_size=1000)

    with harness.connect(local_db) as conn:
        cur = conn.cursor()
        assert _scalar(
            cur, "SELECT is_processed FROM SentianceEventos WHERE id = ?", CHILD_CASE_ID
        ) in (0, False), "orphan child was not left at is_processed = 0"
        assert _scalar(
            cur, "SELECT COUNT(*) FROM SdkSourceEvent WHERE sentiance_eventos_id = ?", CHILD_CASE_ID
        ) == 0, "orphan child must not create an SdkSourceEvent audit row"

    # Step 2: parent arrives -> both must complete.
    harness.load_corpus_cases([_requeued(parent, PARENT_CASE_ID, tid, new_tid)], local_db)
    harness.run_pipeline_to_completion(local_db)

    with harness.connect(local_db) as conn:
        cur = conn.cursor()
        for case_id in (CHILD_CASE_ID, PARENT_CASE_ID):
            assert _scalar(
                cur, "SELECT is_processed FROM SentianceEventos WHERE id = ?", case_id
            ) in (1, True), f"id={case_id} did not reach is_processed = 1"
        child_rows = _scalar(
            cur,
            f"SELECT COUNT(*) FROM {CHILD_TABLE_BY_TIPO[child['tipo']]} c "
            "JOIN SdkSourceEvent s ON s.sdk_source_event_id = c.sdk_source_event_id "
            "WHERE s.sentiance_eventos_id = ?",
            CHILD_CASE_ID,
        )
        assert child_rows >= 1, "retried child produced no rows in its target table"
