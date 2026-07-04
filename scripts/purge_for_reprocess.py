"""
purge_for_reprocess.py — Clean-slate purge to safely reprocess a window
=======================================================================

The ETL appends most domain rows unconditionally (Timeline, UserContext,
SdkStatus, ...), so resetting ``is_processed`` to 0 and re-running would
*duplicate* them. This maintenance tool wipes every downstream row produced
by a set of ``SentianceEventos`` rows — following the ``SdkSourceEvent`` audit
link and the UserContext sub-tree — and resets those rows to ``is_processed=0``
so the next normal ETL run rebuilds them from scratch, with no duplicates.

It does NOT touch the ingestion hot path (``sentiance_etl.py``): reprocessing
is a rare maintenance action, so the logic lives here instead of complicating
every INSERT in ``run()``.

USAGE
-----
    # Reprocess one user's history
    python scripts/purge_for_reprocess.py --uid 6a1c27f2...

    # Reprocess a date window (SentianceEventos.fechahora)
    python scripts/purge_for_reprocess.py --since 2026-07-01 --until 2026-08-01

    # Specific rows
    python scripts/purge_for_reprocess.py --ids 101,102,103

    # Preview only — counts what WOULD be deleted, writes nothing
    python scripts/purge_for_reprocess.py --since 2026-07-01 --dry-run

    # Then run the ETL to rebuild:
    python etl/run_full_pipeline.py

The target database is whatever ``.env`` points at (DB_SERVER/PORT/USER/
PASSWORD/NAME) — set it deliberately before running.

CAVEAT — purge complete windows
-------------------------------
``Trip`` / ``DrivingInsightsTrip`` are shared across the several events that
build a trip. A purge deletes a Trip when any targeted event created or last
updated it; the trip is rebuilt only if its source events are reprocessed too.
Target whole trips (by ``--uid`` or a wide ``--since/--until``), not arbitrary
individual rows, or a trip may be dropped without being rebuilt.

``UserMetadata`` has no SdkSourceEvent link so the purge skips it, but it does
not need purging: ``process_metadata`` guards its INSERT with NOT EXISTS on
(user, label, value), so reprocessing never duplicates it (distinct values for
a label still accumulate on purpose).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

import pyodbc
from dotenv import load_dotenv

# override=True: .env is the source of truth, beating any stale shell exports.
load_dotenv(override=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("purge_for_reprocess")

# Delete order matters: children before parents. Each entry is a DELETE whose
# WHERE clause narrows to the targeted rows via #tgt (SentianceEventos ids) and
# the SdkSourceEvent audit link (#sids). UserContext sub-tree first, then the
# DrivingInsights sub-tree, then the flat per-event tables, then Trip, then the
# audit rows themselves.
_HEADERS = (
    "SELECT user_context_payload_id FROM UserContextHeader "
    "WHERE sdk_source_event_id IN (SELECT sid FROM #sids)"
)
_DI_TRIPS = (
    "SELECT driving_insights_trip_id FROM DrivingInsightsTrip "
    "WHERE sdk_source_event_id IN (SELECT sid FROM #sids)"
)

DELETE_STEPS: list[tuple[str, str]] = [
    ("UserContextSegmentAttribute",
     "DELETE FROM UserContextSegmentAttribute WHERE user_context_active_segment_detail_id IN "
     "(SELECT user_context_active_segment_detail_id FROM UserContextActiveSegmentDetail "
     f"WHERE user_context_payload_id IN ({_HEADERS}))"),
    ("UserContextActiveSegmentDetail",
     f"DELETE FROM UserContextActiveSegmentDetail WHERE user_context_payload_id IN ({_HEADERS})"),
    ("UserContextEventDetail",
     f"DELETE FROM UserContextEventDetail WHERE user_context_payload_id IN ({_HEADERS})"),
    ("UserHomeHistory",
     f"DELETE FROM UserHomeHistory WHERE user_context_payload_id IN ({_HEADERS})"),
    ("UserWorkHistory",
     f"DELETE FROM UserWorkHistory WHERE user_context_payload_id IN ({_HEADERS})"),
    ("UserContextUpdateCriteria",
     f"DELETE FROM UserContextUpdateCriteria WHERE user_context_payload_id IN ({_HEADERS})"),
    ("UserContextHeader",
     "DELETE FROM UserContextHeader WHERE sdk_source_event_id IN (SELECT sid FROM #sids)"),
    ("DrivingInsightsHarshEvent",
     "DELETE FROM DrivingInsightsHarshEvent WHERE sdk_source_event_id IN (SELECT sid FROM #sids) "
     f"OR driving_insights_trip_id IN ({_DI_TRIPS})"),
    ("DrivingInsightsPhoneEvent",
     "DELETE FROM DrivingInsightsPhoneEvent WHERE sdk_source_event_id IN (SELECT sid FROM #sids) "
     f"OR driving_insights_trip_id IN ({_DI_TRIPS})"),
    ("DrivingInsightsCallEvent",
     "DELETE FROM DrivingInsightsCallEvent WHERE sdk_source_event_id IN (SELECT sid FROM #sids) "
     f"OR driving_insights_trip_id IN ({_DI_TRIPS})"),
    ("DrivingInsightsSpeedingEvent",
     "DELETE FROM DrivingInsightsSpeedingEvent WHERE sdk_source_event_id IN (SELECT sid FROM #sids) "
     f"OR driving_insights_trip_id IN ({_DI_TRIPS})"),
    ("DrivingInsightsWrongWayDrivingEvent",
     "DELETE FROM DrivingInsightsWrongWayDrivingEvent WHERE sdk_source_event_id IN (SELECT sid FROM #sids) "
     f"OR driving_insights_trip_id IN ({_DI_TRIPS})"),
    ("DrivingInsightsTrip",
     "DELETE FROM DrivingInsightsTrip WHERE sdk_source_event_id IN (SELECT sid FROM #sids)"),
    ("TimelineEventHistory",
     "DELETE FROM TimelineEventHistory WHERE sdk_source_event_id IN (SELECT sid FROM #sids)"),
    ("UserActivityHistory",
     "DELETE FROM UserActivityHistory WHERE sdk_source_event_id IN (SELECT sid FROM #sids)"),
    ("SdkStatusHistory",
     "DELETE FROM SdkStatusHistory WHERE sdk_source_event_id IN (SELECT sid FROM #sids)"),
    ("TechnicalEventHistory",
     "DELETE FROM TechnicalEventHistory WHERE sdk_source_event_id IN (SELECT sid FROM #sids)"),
    ("VehicleCrashEvent",
     "DELETE FROM VehicleCrashEvent WHERE sdk_source_event_id IN (SELECT sid FROM #sids)"),
    ("Trip",
     "DELETE FROM Trip WHERE creating_sdk_source_event_id IN (SELECT sid FROM #sids) "
     "OR last_updated_by_sdk_source_event_id IN (SELECT sid FROM #sids)"),
    ("SdkSourceEvent",
     "DELETE FROM SdkSourceEvent WHERE sentiance_eventos_id IN (SELECT id FROM #tgt)"),
]


def get_conn() -> pyodbc.Connection:
    server, port = os.getenv("DB_SERVER"), os.getenv("DB_PORT")
    user, pwd, db = os.getenv("DB_USER"), os.getenv("DB_PASSWORD"), os.getenv("DB_NAME")
    if not all([server, port, user, pwd, db]):
        raise ValueError("Faltan variables DB_* en .env")
    conn_str = (
        f"DRIVER={{ODBC Driver 18 for SQL Server}};SERVER={server},{port};"
        f"DATABASE={db};UID={user};PWD={pwd};Encrypt=yes;TrustServerCertificate=yes"
    )
    return pyodbc.connect(conn_str, autocommit=False)


def _date_column(conn: pyodbc.Connection) -> str:
    """Pick the SentianceEventos timestamp column, portable across schemas.

    Production/RDS carries the event time in ``fechahora``; the local/init
    schema only has the ingestion time ``created_at``. Prefer the former.
    """
    cur = conn.cursor()
    cur.execute(
        "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_NAME = 'SentianceEventos' AND COLUMN_NAME IN ('fechahora', 'created_at')"
    )
    cols = {r[0].lower() for r in cur.fetchall()}
    return "fechahora" if "fechahora" in cols else "created_at"


def resolve_target_ids(
    conn: pyodbc.Connection,
    ids: list[int] | None,
    uid: str | None,
    since: str | None,
    until: str | None,
) -> list[int]:
    if ids:
        return ids
    sql = "SELECT id FROM SentianceEventos WHERE 1=1"
    params: list[str] = []
    if uid:
        sql += " AND sentianceid = ?"
        params.append(uid)
    if since or until:
        col = _date_column(conn)
        if since:
            sql += f" AND {col} >= ?"
            params.append(since)
        if until:
            sql += f" AND {col} < ?"
            params.append(until)
    cur = conn.cursor()
    cur.execute(sql, params)
    return [row[0] for row in cur.fetchall()]


def _load_targets(conn: pyodbc.Connection, target_ids: list[int]) -> None:
    """Materialise #tgt (SentianceEventos ids) and #sids (their SdkSourceEvent ids)."""
    cur = conn.cursor()
    cur.execute("CREATE TABLE #tgt (id INT PRIMARY KEY)")
    cur.fast_executemany = True
    cur.executemany("INSERT INTO #tgt (id) VALUES (?)", [(i,) for i in target_ids])
    cur.execute(
        "SELECT sdk_source_event_id AS sid INTO #sids FROM SdkSourceEvent "
        "WHERE sentiance_eventos_id IN (SELECT id FROM #tgt)"
    )


def purge(conn: pyodbc.Connection, target_ids: list[int], dry_run: bool = False) -> dict[str, int]:
    """Delete all downstream rows for target_ids and reset them to is_processed=0.

    Returns a per-table dict of rows deleted (rows that WOULD be deleted when
    dry_run). Runs in the caller's transaction; commits on success unless
    dry_run, which rolls back.
    """
    counts: dict[str, int] = {}
    cur = conn.cursor()
    _load_targets(conn, target_ids)

    for table, delete_sql in DELETE_STEPS:
        if dry_run:
            # Count via the same predicate without deleting.
            where = delete_sql.split(" WHERE ", 1)[1]
            cur.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}")
            counts[table] = cur.fetchone()[0]
        else:
            cur.execute(delete_sql)
            counts[table] = cur.rowcount

    if dry_run:
        cur.execute("SELECT COUNT(*) FROM #tgt")
        counts["SentianceEventos (reset->0)"] = cur.fetchone()[0]
        conn.rollback()
    else:
        cur.execute("UPDATE SentianceEventos SET is_processed = 0 WHERE id IN (SELECT id FROM #tgt)")
        counts["SentianceEventos (reset->0)"] = cur.rowcount
        conn.commit()
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Clean-slate purge to reprocess a window.")
    parser.add_argument("--ids", help="Comma-separated SentianceEventos ids")
    parser.add_argument("--uid", help="Only rows for this sentianceid (user)")
    parser.add_argument("--since", help="fechahora >= this (YYYY-MM-DD)")
    parser.add_argument("--until", help="fechahora < this (YYYY-MM-DD)")
    parser.add_argument("--dry-run", action="store_true", help="Count only, write nothing")
    parser.add_argument("--yes", action="store_true", help="Skip the confirmation prompt")
    args = parser.parse_args(argv)

    if not any([args.ids, args.uid, args.since, args.until]):
        parser.error("provide at least one of --ids / --uid / --since / --until")

    ids = [int(x) for x in args.ids.split(",")] if args.ids else None

    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT DB_NAME()")
        logger.info("Target database: %s", cur.fetchone()[0])

        target_ids = resolve_target_ids(conn, ids, args.uid, args.since, args.until)
        if not target_ids:
            logger.info("No SentianceEventos rows match the criteria — nothing to do.")
            return 0
        logger.info("Matched %d SentianceEventos row(s).", len(target_ids))

        if not args.dry_run and not args.yes:
            resp = input(f"Purge downstream for {len(target_ids)} row(s) and reset them? [y/N] ")
            if resp.strip().lower() not in ("y", "yes"):
                logger.info("Aborted.")
                return 1

        counts = purge(conn, target_ids, dry_run=args.dry_run)
        verb = "would delete" if args.dry_run else "deleted"
        for table, n in counts.items():
            if n:
                logger.info("  %s %d from %s", verb, n, table)
        logger.info("Done%s.", " (dry-run, rolled back)" if args.dry_run else "")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
