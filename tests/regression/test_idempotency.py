"""
test_idempotency.py — A second ETL pass over a drained queue must change nothing.

The ETL's only re-entry contract is the is_processed flag: rows at 1/-1 are
never refetched, and orphan children at 0 are refetched but skipped until
their parent exists. Therefore an extra run() over the post-pipeline queue
must leave every table byte-identical. A failure here means double-insertion,
a MERGE that is not idempotent, or a row being reprocessed when it should not be.
"""

from __future__ import annotations

import pytest

from . import snapshot_lib

pytestmark = pytest.mark.regression


def test_second_pass_is_a_noop(pipeline_state) -> None:
    diff = snapshot_lib.diff_states(pipeline_state.dump_run1, pipeline_state.dump_run2)
    assert diff == "", (
        "Re-running the ETL over the drained queue modified the database — "
        "the pipeline is not idempotent:\n\n" + diff
    )
