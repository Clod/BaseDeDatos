"""test_purge_reprocess.py — purge + reprocess is a clean, duplicate-free rebuild.

Drives scripts/purge_for_reprocess.py end to end against the local corpus DB:
snapshot per-table counts, purge every processed row (which wipes the downstream
tables and resets is_processed to 0), confirm the tables are empty, then run the
ETL to completion and assert every table is rebuilt to its exact original size —
no duplicates, no losses.

Mutates and rebuilds the live post-pipeline DB, so it depends on
`pipeline_state` (runs after the canonical cycle) and is named to sort after the
live-DB invariant/ordering tests. The frozen snapshot tests are unaffected.
"""

from __future__ import annotations

import os
import sys

import pytest

from . import harness

pytestmark = pytest.mark.regression

_SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "scripts")
sys.path.insert(0, _SCRIPTS)
import purge_for_reprocess as purge_mod  # noqa: E402

# Tables the purge is responsible for (order-independent for counting).
PURGED_TABLES = [t for t, _ in purge_mod.DELETE_STEPS]


def _counts(cur, tables) -> dict[str, int]:
    out: dict[str, int] = {}
    for t in tables:
        cur.execute(f"SELECT COUNT(*) FROM {t}")
        out[t] = cur.fetchone()[0]
    return out


def test_purge_then_reprocess_rebuilds_identically(local_db, pipeline_state) -> None:
    conn = harness.connect(local_db)
    try:
        before = _counts(conn.cursor(), PURGED_TABLES)

        cur = conn.cursor()
        cur.execute("SELECT id FROM SentianceEventos WHERE is_processed = 1")
        target_ids = [r[0] for r in cur.fetchall()]
        assert target_ids, "corpus produced no processed rows to purge"

        deleted = purge_mod.purge(conn, target_ids, dry_run=False)
    finally:
        conn.close()

    # After purge every downstream table must be empty.
    conn = harness.connect(local_db)
    try:
        after_purge = _counts(conn.cursor(), PURGED_TABLES)
    finally:
        conn.close()
    non_empty = {t: n for t, n in after_purge.items() if n}
    assert not non_empty, f"purge left rows behind: {non_empty}\ndeleted report: {deleted}"

    # Reprocess from the clean slate.
    harness.run_pipeline_to_completion(local_db)

    conn = harness.connect(local_db)
    try:
        after = _counts(conn.cursor(), PURGED_TABLES)
    finally:
        conn.close()

    grown_or_shrunk = {t: (before[t], after[t]) for t in PURGED_TABLES if before[t] != after[t]}
    assert not grown_or_shrunk, (
        "purge + reprocess did not rebuild the tables to their original size "
        "(before -> after):\n"
        + "\n".join(f"  {t}: {b} -> {a}" for t, (b, a) in grown_or_shrunk.items())
    )
