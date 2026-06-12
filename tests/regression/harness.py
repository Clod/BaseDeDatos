"""
harness.py — Database lifecycle helpers for the regression suite.

Everything here is DESTRUCTIVE to the local Docker database (VictaTMTK is
dropped and recreated from development/sql/init_db.sql on every run), so two
hard safety rails are enforced before any connection is opened:

1. The target host must be localhost / 127.0.0.1. Anything else aborts.
2. ENABLE_MOVILIDAD_BRIDGE is forced to "false" so the ETL can never reach
   out to the external Movilidad server during a test run.

Production credentials never appear here: the harness only knows the local
Docker instance (development/docker-compose.yml).
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pyodbc

logger = logging.getLogger("regression.harness")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
INIT_SQL = PROJECT_ROOT / "development" / "sql" / "init_db.sql"
CORPUS_CASES_DIR = Path(__file__).parent / "corpus" / "cases"

LOCAL_HOSTS = {"localhost", "127.0.0.1"}


@dataclass(frozen=True)
class LocalDb:
    """Connection settings for the local Docker SQL Server (Azure SQL Edge)."""

    host: str = "localhost"
    port: str = "1433"
    user: str = "sa"
    password: str = "SentianceLocal2026!"
    database: str = "VictaTMTK"

    def conn_str(self, database: str | None = None) -> str:
        return (
            "DRIVER={ODBC Driver 18 for SQL Server};"
            f"SERVER={self.host},{self.port};DATABASE={database or self.database};"
            f"UID={self.user};PWD={self.password};Encrypt=yes;TrustServerCertificate=yes"
        )


def assert_local_only(db: LocalDb) -> None:
    """Aborts unless the target host is the local Docker instance."""
    if db.host not in LOCAL_HOSTS:
        raise RuntimeError(
            f"Regression harness refuses to run against host '{db.host}'. "
            "Only localhost is allowed — this suite DROPS the database."
        )


def connect(db: LocalDb, database: str | None = None, autocommit: bool = False) -> pyodbc.Connection:
    assert_local_only(db)
    return pyodbc.connect(db.conn_str(database), autocommit=autocommit, timeout=5)


def is_db_reachable(db: LocalDb) -> bool:
    """True if the local Docker SQL Server answers within the timeout."""
    try:
        with connect(db, database="master", autocommit=True):
            return True
    except pyodbc.Error:
        return False


def _run_sql_script(cursor: Any, path: Path) -> None:
    """Executes a .sql file on an autocommit cursor, splitting on GO."""
    batch: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip().upper() == "GO":
            if any(piece.strip() for piece in batch):
                cursor.execute("\n".join(batch))
            batch = []
        else:
            batch.append(line)
    if any(piece.strip() for piece in batch):
        cursor.execute("\n".join(batch))


def recreate_schema(db: LocalDb) -> None:
    """Drops VictaTMTK and rebuilds it from init_db.sql (identity seeds reset)."""
    assert_local_only(db)
    logger.info("Recreating %s schema on %s:%s", db.database, db.host, db.port)
    with connect(db, database="master", autocommit=True) as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"IF EXISTS (SELECT 1 FROM sys.databases WHERE name = '{db.database}') "
            f"BEGIN ALTER DATABASE [{db.database}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; "
            f"DROP DATABASE [{db.database}]; END"
        )
        cursor.execute(f"CREATE DATABASE [{db.database}]")
        _run_sql_script(cursor, INIT_SQL)


def _to_sql_datetime(value: str | None) -> str | None:
    """ISO-8601 -> 'YYYY-MM-DD HH:MM:SS.mmm' (same convention as ETL.format_ts)."""
    if not value:
        return None
    return value.replace("Z", "").replace("T", " ")[:23]


def load_corpus_cases(cases: list[dict[str, Any]] | None = None, db: LocalDb = LocalDb()) -> int:
    """Inserts corpus cases into SentianceEventos with their original ids.

    Cases default to every file in corpus/cases/, loaded in id order so the
    queue (and therefore every downstream identity value) is deterministic.
    """
    if cases is None:
        cases = read_corpus_cases()
    with connect(db) as conn:
        cursor = conn.cursor()
        cursor.execute("SET IDENTITY_INSERT SentianceEventos ON")
        for case in cases:
            meta = case.get("meta", {})
            cursor.execute(
                "INSERT INTO SentianceEventos "
                "(id, sentianceid, json, tipo, created_at, app_version, is_processed) "
                "VALUES (?, ?, ?, ?, ?, ?, 0)",
                (
                    case["id"],
                    case.get("sentianceid"),
                    case["json"],
                    case["tipo"],
                    _to_sql_datetime(meta.get("created_at")) or "2026-01-01 00:00:00.000",
                    meta.get("app_version") or "regression-corpus",
                ),
            )
        cursor.execute("SET IDENTITY_INSERT SentianceEventos OFF")
        conn.commit()
    logger.info("Loaded %d corpus cases into SentianceEventos", len(cases))
    return len(cases)


def read_corpus_cases() -> list[dict[str, Any]]:
    """Reads every committed corpus case, sorted by id."""
    cases = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(CORPUS_CASES_DIR.glob("*.json"))
    ]
    return sorted(cases, key=lambda c: c["id"])


def make_etl(db: LocalDb = LocalDb()) -> Any:
    """Builds a SentianceETL wired to the local DB with the bridge disabled."""
    assert_local_only(db)
    os.environ.update(
        {
            "DB_SERVER": db.host,
            "DB_PORT": db.port,
            "DB_USER": db.user,
            "DB_PASSWORD": db.password,
            "DB_NAME": db.database,
            "ENABLE_MOVILIDAD_BRIDGE": "false",
        }
    )
    from sentiance_etl import SentianceETL  # imported late: reads env at init

    return SentianceETL()


def run_pipeline_to_completion(db: LocalDb = LocalDb(), max_passes: int = 20) -> int:
    """Runs ETL batches until the queue stops moving. Returns passes used.

    Mirrors run_full_pipeline.py: run() returns False when the queue is empty
    or only orphan children remain — both are terminal states for a fixed corpus.
    """
    etl = make_etl(db)
    for n_pass in range(1, max_passes + 1):
        if not etl.run(batch_size=1000):
            return n_pass
    raise RuntimeError(f"Pipeline did not drain the queue in {max_passes} passes")
