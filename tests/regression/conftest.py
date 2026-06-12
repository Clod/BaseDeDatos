"""
conftest.py — Fixtures for the golden-snapshot regression suite.

The whole suite hangs off one session-scoped fixture, `pipeline_state`,
which performs the canonical regression cycle exactly once:

    recreate schema -> load corpus -> run ETL to completion -> dump (run 1)
                                   -> run ETL once more     -> dump (run 2)

Both dumps are frozen before any test executes, so later tests (e.g. the
orphan-ordering test, which inserts extra rows) cannot contaminate them.

Gating: these tests DROP the local VictaTMTK database, so they only run when
explicitly requested with --run-regression. Without the flag, or when the
local Docker DB is unreachable, every test is skipped — `pytest` from the
project root stays safe and fast.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from . import harness, snapshot_lib


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    for item in items:
        if "tests/regression" in str(item.fspath).replace("\\", "/"):
            item.add_marker(pytest.mark.regression)


@dataclass(frozen=True)
class PipelineState:
    """Frozen result of the canonical regression cycle."""

    dump_run1: dict[str, list[str]]
    dump_run2: dict[str, list[str]]
    passes: int
    n_cases: int


@pytest.fixture(scope="session")
def local_db(request: pytest.FixtureRequest) -> harness.LocalDb:
    if not request.config.getoption("--run-regression"):
        pytest.skip("regression suite runs only with --run-regression (drops the local DB)")
    db = harness.LocalDb()
    harness.assert_local_only(db)
    if not harness.is_db_reachable(db):
        pytest.skip(
            "local Docker SQL Server is not reachable on localhost:1433 "
            "(cd development && docker-compose up -d)"
        )
    return db


@pytest.fixture(scope="session")
def pipeline_state(local_db: harness.LocalDb) -> PipelineState:
    cases = harness.read_corpus_cases()
    if not cases:
        pytest.skip("corpus is empty — run corpus_builder.py first (see README.md)")

    harness.recreate_schema(local_db)
    n_cases = harness.load_corpus_cases(cases, local_db)
    passes = harness.run_pipeline_to_completion(local_db)

    with harness.connect(local_db) as conn:
        dump_run1 = snapshot_lib.dump_db_state(conn.cursor())

    # One extra pass over the already-drained queue: must be a strict no-op.
    etl = harness.make_etl(local_db)
    etl.run(batch_size=1000)
    with harness.connect(local_db) as conn:
        dump_run2 = snapshot_lib.dump_db_state(conn.cursor())

    return PipelineState(dump_run1, dump_run2, passes, n_cases)


@pytest.fixture()
def db_cursor(local_db: harness.LocalDb, pipeline_state: PipelineState):
    """Fresh cursor on the post-pipeline database (for invariant queries)."""
    conn = harness.connect(local_db)
    try:
        yield conn.cursor()
    finally:
        conn.close()
