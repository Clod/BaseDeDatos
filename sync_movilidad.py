"""
sync_movilidad.py — Backfill de Movilidad desde VictaTMTK
==========================================================

Sincroniza los trips ya procesados en VictaTMTK hacia las tablas de Movilidad
sin necesidad de reprocesar SentianceEventos. Útil cuando el bridge se activa
después de que el ETL ya procesó registros existentes.

USAGE:
    # Todos los trips
    python sync_movilidad.py

    # Solo los trips de un usuario
    python sync_movilidad.py --uid abc123

    # Solo trips procesados desde una fecha
    python sync_movilidad.py --since 2026-05-01

    # Dry-run: muestra qué se sincronizaría sin escribir
    python sync_movilidad.py --dry-run
"""

import argparse
import logging
import os
import sys

import pyodbc
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("sync_movilidad")


def get_victatmtk_conn() -> pyodbc.Connection:
    server = os.getenv("DB_SERVER")
    port = os.getenv("DB_PORT")
    user = os.getenv("DB_USER")
    pwd = os.getenv("DB_PASSWORD")
    db = os.getenv("DB_NAME")
    if not all([server, port, user, pwd, db]):
        raise ValueError("Faltan variables DB_* en .env")
    conn_str = (
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"SERVER={server},{port};DATABASE={db};"
        f"UID={user};PWD={pwd};"
        f"Encrypt=yes;TrustServerCertificate=yes"
    )
    return pyodbc.connect(conn_str)


def get_transport_ids(
    conn: pyodbc.Connection,
    uid: str | None,
    since: str | None,
) -> list[str]:
    sql = "SELECT DISTINCT canonical_transport_event_id FROM Trip WHERE 1=1"
    params: list[str] = []
    if uid:
        sql += " AND sentiance_user_id = ?"
        params.append(uid)
    if since:
        sql += " AND created_at >= ?"
        params.append(since)
    sql += " ORDER BY canonical_transport_event_id"
    cur = conn.cursor()
    cur.execute(sql, params)
    return [row[0] for row in cur.fetchall()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill Movilidad desde VictaTMTK")
    parser.add_argument("--uid", help="Filtrar por sentiance_user_id")
    parser.add_argument("--since", help="Filtrar trips con created_at >= fecha (YYYY-MM-DD)")
    parser.add_argument("--dry-run", action="store_true", help="Solo muestra qué se sincronizaría")
    parser.add_argument("--batch-size", type=int, default=50, help="Transport IDs por batch (default: 50)")
    args = parser.parse_args()

    try:
        from movilidad_bridge import MovilidadBridge
    except ImportError as exc:
        logger.error("No se pudo importar MovilidadBridge: %s", exc)
        sys.exit(1)

    conn = get_victatmtk_conn()
    transport_ids = get_transport_ids(conn, args.uid, args.since)

    if not transport_ids:
        logger.info("No se encontraron trips en VictaTMTK con los filtros dados.")
        return

    logger.info("Trips encontrados: %d", len(transport_ids))

    if args.dry_run:
        logger.info("--dry-run activo: no se escribirá nada.")
        for tid in transport_ids:
            logger.info("  [DRY-RUN] %s", tid)
        return

    bridge = MovilidadBridge(conn)

    total_synced = total_skipped = total_failed = 0
    for i in range(0, len(transport_ids), args.batch_size):
        batch = set(transport_ids[i : i + args.batch_size])
        logger.info(
            "Batch %d/%d (%d trips)...",
            i // args.batch_size + 1,
            -(-len(transport_ids) // args.batch_size),
            len(batch),
        )
        report = bridge.sync_trips(batch)
        total_synced += report.synced
        total_skipped += report.skipped
        total_failed += report.failed
        if report.errors:
            for err in report.errors:
                logger.warning("  Error: %s", err)

    bridge.close()
    conn.close()

    logger.info(
        "Backfill completado — sincronizados: %d | omitidos: %d | fallidos: %d",
        total_synced, total_skipped, total_failed,
    )
    if total_failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
