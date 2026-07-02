"""
ETL Test-DB Bootstrapper — VictaTMTK_ETL (RDS sandbox)
======================================================

DESCRIPTION:
Prepares the `VictaTMTK_ETL` database on the RDS server so the Stage-2 ETL
(etl/sentiance_etl.py) can be run against a real production-sized copy of the
data WITHOUT touching the live `VictaTMTK` database.

`VictaTMTK_ETL` already contains the 14 legacy tables and ~78k rows in
`SentianceEventos`, but it is missing the 22 Stage-2 domain tables and the
`is_processed` column that the ETL needs. This script adds exactly those,
idempotently.

WHY A DEDICATED SCRIPT:
`development/sql/init_db.sql` hardcodes `USE master / CREATE DATABASE VictaTMTK /
USE VictaTMTK`, so it cannot be pointed at `VictaTMTK_ETL` as-is. This script
reuses the SAME CREATE TABLE definitions from that file but strips the database
preamble, so every table lands in whatever database `.env` points at.

This script NEVER runs `development/sql/migrate_prod_stage2.sql` (that file is a
human-only production artifact). It applies only the minimal schema deltas the
test run needs.

SAFETY:
- Refuses to run unless DB_NAME == 'VictaTMTK_ETL' (override with --force).
- Never issues CREATE DATABASE and never runs any USE statement, so it can only
  affect the database it connects to.
- --reset drops and recreates ONLY the 22 Stage-2 tables; it never touches
  `SentianceEventos` data nor the legacy/bridge tables (Transporte, Eventos, ...).

USAGE:
    # First-time setup (creates Stage-2 tables + is_processed column):
    .venv/bin/python development/bootstrap_etl_test_db.py

    # Wipe Stage-2 output and re-arm the queue to test again from scratch:
    .venv/bin/python development/bootstrap_etl_test_db.py --reset
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys

import pyodbc
from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ETL-TestDB-Bootstrap")

# The 22 Stage-2 domain tables (everything init_db.sql creates EXCEPT the two
# landing-zone tables SentianceEventos / SentianceEventos_Errors, which already
# exist in VictaTMTK_ETL and hold the source data we want to keep).
STAGE2_TABLES: tuple[str, ...] = (
    "SdkSourceEvent",
    "UserMetadata",
    "Trip",
    "DrivingInsightsTrip",
    "DrivingInsightsHarshEvent",
    "DrivingInsightsPhoneEvent",
    "DrivingInsightsCallEvent",
    "DrivingInsightsSpeedingEvent",
    "DrivingInsightsWrongWayDrivingEvent",
    "UserContextHeader",
    "UserContextUpdateCriteria",
    "UserHomeHistory",
    "UserWorkHistory",
    "UserContextActiveSegmentDetail",
    "UserContextSegmentAttribute",
    "UserContextEventDetail",
    "TimelineEventHistory",
    "UserActivityHistory",
    "TechnicalEventHistory",
    "VehicleCrashEvent",
    "SdkStatusHistory",
    "UserOrganization",
)

# Batches from init_db.sql that manage the DATABASE itself (not tables). We skip
# these so the schema lands in the already-connected database.
_SKIP_BATCH_RE = re.compile(
    r"\bCREATE\s+DATABASE\b|\bUSE\s+(?:master|VictaTMTK)\b", re.IGNORECASE
)


def _build_conn_str() -> tuple[str, str]:
    """Build an ODBC connection string from the DB_* env vars (same ones the
    ETL uses). Returns (conn_str, db_name)."""
    server = os.getenv("DB_SERVER")
    port = os.getenv("DB_PORT")
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")
    db_name = os.getenv("DB_NAME")

    missing = [
        k
        for k, v in {
            "DB_SERVER": server,
            "DB_PORT": port,
            "DB_USER": user,
            "DB_PASSWORD": password,
            "DB_NAME": db_name,
        }.items()
        if not v
    ]
    if missing:
        logger.error("Faltan variables en el .env: %s", ", ".join(missing))
        sys.exit(1)

    # Driver selection mirrors etl/sentiance_etl.py: honor DB_DRIVER if set,
    # otherwise auto-detect the newest ODBC driver installed (18 → 17 → legacy).
    driver = os.getenv("DB_DRIVER")
    if not driver:
        available = pyodbc.drivers()
        for d in ("ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server", "SQL Server"):
            if d in available:
                driver = d
                break
        if not driver:
            driver = "SQL Server"

    conn_str = (
        f"DRIVER={{{driver}}};"
        f"SERVER={server},{port};"
        f"DATABASE={db_name};"
        f"UID={user};"
        f"PWD={password};"
    )
    if "ODBC Driver" in driver:
        conn_str += "Encrypt=yes;TrustServerCertificate=yes"
    return conn_str, db_name


def _load_stage2_batches() -> list[str]:
    """Read init_db.sql and return only the batches that create Stage-2 objects,
    with the CREATE DATABASE / USE preamble stripped out."""
    script_path = os.path.join(os.path.dirname(__file__), "sql", "init_db.sql")
    if not os.path.exists(script_path):
        logger.error("No se encontró el esquema en: %s", script_path)
        sys.exit(1)

    with open(script_path, "r", encoding="utf-8") as f:
        sql_script = f.read()

    batches: list[str] = []
    for raw in sql_script.split("GO"):
        batch = raw.strip()
        if not batch:
            continue
        if _SKIP_BATCH_RE.search(batch):
            continue  # database-level statement — not for a test DB
        batches.append(batch)
    return batches


def _run_batches(cursor: pyodbc.Cursor, batches: list[str]) -> None:
    for batch in batches:
        try:
            cursor.execute(batch)
        except Exception as exc:  # noqa: BLE001
            msg = str(exc).lower()
            if "already exists" in msg or "there is already an object" in msg:
                continue  # idempotent re-run
            logger.error("Error ejecutando un batch: %s", exc)


def _ensure_is_processed(cursor: pyodbc.Cursor) -> None:
    """Add SentianceEventos.is_processed (SMALLINT) if it is missing. The table
    pre-exists in VictaTMTK_ETL, so init_db.sql's IF NOT EXISTS guard skips it
    and never adds this column — we add it explicitly here."""
    cursor.execute(
        """
        IF NOT EXISTS (
            SELECT 1 FROM sys.columns
            WHERE object_id = OBJECT_ID('dbo.SentianceEventos') AND name = 'is_processed'
        )
            ALTER TABLE dbo.SentianceEventos
                ADD is_processed SMALLINT NOT NULL
                    CONSTRAINT DF_SentianceEventos_is_processed DEFAULT 0;
        """
    )
    # Filtered index that backs the queue scan (WHERE is_processed = 0).
    cursor.execute(
        """
        IF NOT EXISTS (
            SELECT 1 FROM sys.indexes
            WHERE name = 'IX_SentianceEventos_pending'
              AND object_id = OBJECT_ID('dbo.SentianceEventos')
        )
            CREATE INDEX IX_SentianceEventos_pending
                ON dbo.SentianceEventos(id) WHERE is_processed = 0;
        """
    )


def _reset_stage2(cursor: pyodbc.Cursor) -> None:
    """Drop the 22 Stage-2 tables (FKs first) and re-arm the queue. Source data
    in SentianceEventos and the legacy/bridge tables are left untouched."""
    names_sql = ", ".join(f"'{t}'" for t in STAGE2_TABLES)

    # 1. Drop every FK that touches a Stage-2 table (as parent or as referenced).
    cursor.execute(
        f"""
        SELECT 'ALTER TABLE ' + QUOTENAME(s.name) + '.' + QUOTENAME(t.name)
               + ' DROP CONSTRAINT ' + QUOTENAME(fk.name)
        FROM sys.foreign_keys fk
        JOIN sys.tables t  ON fk.parent_object_id = t.object_id
        JOIN sys.schemas s ON t.schema_id = s.schema_id
        WHERE t.name IN ({names_sql})
           OR OBJECT_NAME(fk.referenced_object_id) IN ({names_sql});
        """
    )
    for (stmt,) in cursor.fetchall():
        cursor.execute(stmt)

    # 2. Drop the tables themselves.
    for table in STAGE2_TABLES:
        cursor.execute(f"IF OBJECT_ID('dbo.{table}', 'U') IS NOT NULL DROP TABLE dbo.{table};")

    # 3. Re-arm the whole queue so the next ETL run reprocesses everything.
    cursor.execute("UPDATE dbo.SentianceEventos SET is_processed = 0;")
    logger.info("Reset OK: tablas Stage-2 recreadas y cola re-armada (is_processed = 0).")


# Tables to show a row count for in the summary (ETL output + bridge output).
# The count is only shown if the table exists.
_COUNT_STAGE2 = ("SdkSourceEvent", "Trip", "DrivingInsightsTrip", "UserContextHeader",
                 "TimelineEventHistory", "VehicleCrashEvent")
_COUNT_BRIDGE = ("Transporte", "Recorridos", "Eventos", "PuntajesPrirmariosTr")


def _count(cursor: pyodbc.Cursor, table: str) -> int | None:
    if cursor.execute(f"SELECT OBJECT_ID('dbo.{table}', 'U')").fetchone()[0] is None:
        return None
    return cursor.execute(f"SELECT COUNT(*) FROM dbo.{table}").fetchone()[0]


def _print_summary(cursor: pyodbc.Cursor, db_name: str) -> None:
    cursor.execute(
        f"""
        SELECT
          (SELECT COUNT(*) FROM sys.tables WHERE name IN ({", ".join(f"'{t}'" for t in STAGE2_TABLES)})) AS stage2_tables,
          (SELECT COUNT(*) FROM sys.columns WHERE object_id = OBJECT_ID('dbo.SentianceEventos') AND name = 'is_processed') AS is_processed_col,
          (SELECT COUNT(*) FROM dbo.SentianceEventos WHERE is_processed = 0) AS pending_rows,
          (SELECT COUNT(*) FROM dbo.SentianceEventos) AS total_rows;
        """
    )
    stage2, has_col, pending, total = cursor.fetchone()
    logger.info("---- Resumen de %s ----", db_name)
    logger.info("Tablas Stage-2 presentes : %s / 22", stage2)
    logger.info("Columna is_processed     : %s", "sí" if has_col else "NO")
    logger.info("SentianceEventos         : %s filas (%s pendientes de procesar)", total, pending)

    logger.info("Salida del ETL (Stage-2):")
    for table in _COUNT_STAGE2:
        n = _count(cursor, table)
        logger.info("  %-22s : %s", table, "(no existe)" if n is None else n)

    logger.info("Salida del bridge Movilidad:")
    for table in _COUNT_BRIDGE:
        n = _count(cursor, table)
        logger.info("  %-22s : %s", table, "(no existe)" if n is None else n)

    if stage2 == 22 and has_col:
        logger.info("La base está lista para correr el ETL.")
    else:
        logger.warning("La base NO quedó completa — revisá los errores de arriba.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepara VictaTMTK_ETL para probar el ETL.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Borra la salida Stage-2 y re-arma la cola para probar de nuevo desde cero.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Permite correr contra un DB_NAME distinto de 'VictaTMTK_ETL'.",
    )
    args = parser.parse_args()

    load_dotenv()
    conn_str, db_name = _build_conn_str()

    if db_name != "VictaTMTK_ETL" and not args.force:
        logger.error(
            "Este script es solo para la base de prueba 'VictaTMTK_ETL', pero el "
            ".env apunta a '%s'. Corregí DB_NAME en el .env (o usá --force si "
            "realmente sabés lo que hacés).",
            db_name,
        )
        sys.exit(1)

    logger.info("Conectando a %s ...", db_name)
    try:
        conn = pyodbc.connect(conn_str, autocommit=True)
    except Exception as exc:  # noqa: BLE001
        logger.error("No se pudo conectar: %s", exc)
        sys.exit(1)

    try:
        cursor = conn.cursor()

        batches = _load_stage2_batches()
        logger.info("Aplicando %s batches de esquema (idempotente)...", len(batches))
        _run_batches(cursor, batches)

        _ensure_is_processed(cursor)

        if args.reset:
            _reset_stage2(cursor)
            # Recreate the freshly-dropped tables.
            _run_batches(cursor, batches)

        _print_summary(cursor, db_name)
    finally:
        conn.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Abortado por el usuario.")
