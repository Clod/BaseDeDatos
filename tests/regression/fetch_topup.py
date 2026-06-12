"""
fetch_topup.py — READ-ONLY production fetcher for corpus top-ups.

Pulls specific SentianceEventos rows from the production RDS instance and
writes them to tests/regression/corpus/sources/ in the standard source-dump
format consumed by corpus_builder.py. This is the tool behind the recurring
"topping up the corpus" procedure (README.md): as production accumulates
traffic for event types the corpus does not cover yet, this script harvests
real representatives for them. It never writes to the database — SELECTs only.

Credentials: read from .env.rds at the project root (never committed).

Usage:
    # Explicit rows (ids chosen by a prior survey):
    python tests/regression/fetch_topup.py --ids 29182 29184 29187

    # Shape-sample a tipo: pulls the (id, length) histogram, fetches
    # K candidates spread across the size distribution, keeps one per
    # structural shape:
    python tests/regression/fetch_topup.py --sample-tipo TimelineUpdate \
        --candidates 14 --max-len 20000

Rows at-or-after the corpus epoch are refused: snapshot masking relies on
every corpus event predating snapshot_lib.CORPUS_EPOCH.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

import pyodbc
from dotenv import dotenv_values

sys.path.insert(0, str(Path(__file__).parent))
from corpus_builder import shape_fingerprint  # noqa: E402
from snapshot_lib import CORPUS_EPOCH  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("fetch_topup")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCES_DIR = Path(__file__).parent / "corpus" / "sources"

SELECT_COLS = "id, sentianceid, json, tipo, created_at, app_version"


def connect_rds() -> pyodbc.Connection:
    env = dotenv_values(PROJECT_ROOT / ".env.rds")
    required = ["DB_SERVER", "DB_PORT", "DB_USER", "DB_PASSWORD", "DB_NAME"]
    if not all(env.get(k) for k in required):
        raise SystemExit(".env.rds is missing or incomplete — cannot reach production.")
    conn_str = (
        "DRIVER={ODBC Driver 18 for SQL Server};"
        f"SERVER={env['DB_SERVER']},{env['DB_PORT']};DATABASE={env['DB_NAME']};"
        f"UID={env['DB_USER']};PWD={env['DB_PASSWORD']};"
        "Encrypt=yes;TrustServerCertificate=yes;ApplicationIntent=ReadOnly"
    )
    logger.info("Connecting (read-only) to %s ...", env["DB_SERVER"])
    return pyodbc.connect(conn_str)


def _row_to_record(row: pyodbc.Row) -> dict:
    rid, sentianceid, payload, tipo, created_at, app_version = row
    if created_at and created_at >= CORPUS_EPOCH:
        raise SystemExit(
            f"Row id={rid} created_at={created_at} is at/after CORPUS_EPOCH "
            f"({CORPUS_EPOCH:%Y-%m-%d}). Bump the epoch in snapshot_lib.py first "
            "(and re-bless), or pick an older row."
        )
    return {
        "original_id": rid,
        "sentianceid": sentianceid,
        "json": payload,
        "tipo": tipo,
        "created_at": created_at.isoformat() if created_at else None,
        "app_version": app_version,
    }


def fetch_by_ids(cursor: pyodbc.Cursor, ids: list[int]) -> list[dict]:
    records = []
    for rid in ids:
        cursor.execute(f"SELECT {SELECT_COLS} FROM SentianceEventos WHERE id = ?", rid)
        row = cursor.fetchone()
        if row is None:
            logger.warning("id=%d not found in production — skipped", rid)
            continue
        records.append(_row_to_record(row))
        logger.info("Fetched id=%d tipo=%s (%d chars)", rid, row[3], len(row[2] or ""))
    return records


def sample_tipo(
    cursor: pyodbc.Cursor, tipo: str, candidates: int, max_len: int
) -> list[dict]:
    """Fetches candidate payloads spread over the size distribution, then
    keeps the lowest-id representative of each distinct structural shape."""
    cursor.execute(
        "SELECT id, LEN(json) FROM SentianceEventos "
        "WHERE tipo = ? AND created_at < ? AND LEN(json) <= ? ORDER BY LEN(json), id",
        (tipo, CORPUS_EPOCH, max_len),
    )
    histogram = cursor.fetchall()
    if not histogram:
        logger.warning("No production rows for tipo=%s under %d chars", tipo, max_len)
        return []
    logger.info("tipo=%s: %d rows in scope; sampling %d candidates", tipo, len(histogram), candidates)

    step = max(1, len(histogram) // max(1, candidates - 1))
    picked = {histogram[i][0] for i in range(0, len(histogram), step)} | {histogram[-1][0]}

    by_shape: dict[str, dict] = {}
    for rid in sorted(picked):
        cursor.execute(f"SELECT {SELECT_COLS} FROM SentianceEventos WHERE id = ?", rid)
        record = _row_to_record(cursor.fetchone())
        try:
            fingerprint = shape_fingerprint(json.loads(record["json"]))
        except (json.JSONDecodeError, TypeError):
            logger.warning("id=%d has unparseable json — skipped", rid)
            continue
        if fingerprint not in by_shape:
            by_shape[fingerprint] = record
            logger.info("  shape %s -> id=%d (%d chars)", fingerprint, rid, len(record["json"]))
    logger.info("tipo=%s: kept %d shape representatives", tipo, len(by_shape))
    return list(by_shape.values())


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only production corpus top-up fetcher")
    parser.add_argument("--ids", nargs="*", type=int, default=[])
    parser.add_argument("--sample-tipo", action="append", default=[])
    parser.add_argument("--candidates", type=int, default=12)
    parser.add_argument("--max-len", type=int, default=20000)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    if not args.ids and not args.sample_tipo:
        parser.error("nothing to do: pass --ids and/or --sample-tipo")

    conn = connect_rds()
    try:
        cursor = conn.cursor()
        records = fetch_by_ids(cursor, args.ids)
        for tipo in args.sample_tipo:
            records += sample_tipo(cursor, tipo, args.candidates, args.max_len)
    finally:
        conn.close()

    out = args.out or SOURCES_DIR / f"prod_topup_{datetime.now():%Y-%m-%d}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    existing: list[dict] = []
    if out.exists():
        existing = json.loads(out.read_text(encoding="utf-8"))
        known = {r["original_id"] for r in existing}
        records = [r for r in records if r["original_id"] not in known]
        logger.info("Appending to existing %s (%d records already there)", out.name, len(existing))
    out.write_text(
        json.dumps(existing + records, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    logger.info("Wrote %d new records to %s", len(records), out)


if __name__ == "__main__":
    main()
