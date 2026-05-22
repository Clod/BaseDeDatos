"""
Local Database Hydrator - Development Utility
============================================

DESCRIPTION:
This script populates the local SQL Server (Docker) with sample Sentiance
payloads. It supports reading directly from compressed GZIP files (.json.gz).

USAGE:
    python hydrate_local_db.py                    # Default: clear & hydrate
    python hydrate_local_db.py --recreate        # Drop & recreate schema, then hydrate
    python hydrate_local_db.py --recreate-only   # Drop & recreate schema only
    python hydrate_local_db.py --no-clear        # Hydrate without clearing tables
"""

import json
import pyodbc
import os
import logging
import gzip
import argparse

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("Hydrator")


def _run_sql_file(cursor, sql_file: str):
    """Executes a SQL file against an already-open cursor, splitting on GO."""
    with open(sql_file, "r") as f:
        sql_script = f.read()
    sql_batch = ""
    for line in sql_script.split("\n"):
        if line.strip().upper() == "GO":
            if sql_batch.strip():
                cursor.execute(sql_batch)
                sql_batch = ""
        else:
            sql_batch += "\n" + line
    if sql_batch.strip():
        cursor.execute(sql_batch)


def recreate_schema():
    """Drop and recreate the VictaTMTK database schema from init_db.sql."""
    server, username, password = "localhost", "sa", "SentianceLocal2026!"
    master_conn_str = f"DRIVER={{ODBC Driver 18 for SQL Server}};SERVER={server};DATABASE=master;UID={username};PWD={password};Encrypt=yes;TrustServerCertificate=yes"

    try:
        logger.info("Connecting to master to drop database...")
        conn = pyodbc.connect(master_conn_str, autocommit=True)
        cursor = conn.cursor()

        # Drop database (autocommit mode required for ALTER DATABASE)
        cursor.execute("""
            IF EXISTS (SELECT * FROM sys.databases WHERE name = 'VictaTMTK')
            BEGIN
                ALTER DATABASE VictaTMTK SET SINGLE_USER WITH ROLLBACK IMMEDIATE;
                DROP DATABASE VictaTMTK;
            END
        """)
        logger.info("Database 'VictaTMTK' dropped.")

        script_dir = os.path.dirname(os.path.abspath(__file__))
        sql_file = os.path.join(script_dir, "sql", "init_db.sql")
        logger.info(f"Reading schema from {sql_file}...")
        _run_sql_file(cursor, sql_file)

        logger.info("VictaTMTK schema recreated successfully.")
        conn.close()
    except Exception as e:
        logger.error(f"Failed to recreate VictaTMTK schema: {e}")
        raise


def recreate_movilidad_schema():
    """Drop and recreate the local Movilidad database schema from init_movilidad.sql."""
    server, username, password = "localhost", "sa", "SentianceLocal2026!"
    master_conn_str = f"DRIVER={{ODBC Driver 18 for SQL Server}};SERVER={server};DATABASE=master;UID={username};PWD={password};Encrypt=yes;TrustServerCertificate=yes"

    try:
        logger.info("Recreating local Movilidad database...")
        conn = pyodbc.connect(master_conn_str, autocommit=True)
        cursor = conn.cursor()

        cursor.execute("""
            IF EXISTS (SELECT * FROM sys.databases WHERE name = 'Movilidad')
            BEGIN
                ALTER DATABASE Movilidad SET SINGLE_USER WITH ROLLBACK IMMEDIATE;
                DROP DATABASE Movilidad;
            END
        """)
        logger.info("Database 'Movilidad' dropped.")

        script_dir = os.path.dirname(os.path.abspath(__file__))
        sql_file = os.path.join(script_dir, "sql", "init_movilidad.sql")
        logger.info(f"Reading schema from {sql_file}...")
        _run_sql_file(cursor, sql_file)

        logger.info("Movilidad schema recreated successfully.")
        conn.close()
    except Exception as e:
        logger.error(f"Failed to recreate Movilidad schema: {e}")
        raise


def hydrate(json_file="sample_payloads.json.gz", clear_first=True, limit=None):
    server, database, username, password = (
        "localhost",
        "VictaTMTK",
        "sa",
        "SentianceLocal2026!",
    )
    conn_str = f"DRIVER={{ODBC Driver 18 for SQL Server}};SERVER={server};DATABASE={database};UID={username};PWD={password};Encrypt=yes;TrustServerCertificate=yes"

    if not os.path.exists(json_file):
        logger.error(f"Sample file '{json_file}' not found.")
        return

    logger.info(f"Opening compressed data file: {json_file}")
    try:
        # Detect if file is gzipped based on extension
        if json_file.endswith(".gz"):
            with gzip.open(json_file, "rt", encoding="utf-8") as f:
                records = json.load(f)
        else:
            with open(json_file, "r") as f:
                records = json.load(f)
    except Exception as e:
        logger.error(f"Failed to read data file: {e}")
        return

    if limit:
        records = records[:limit]
        logger.info(f"Limiting to {limit} records")

    try:
        logger.info(f"Connecting to local database '{database}'...")
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()

        if clear_first:
            logger.info("Clearing local tables for fresh start...")
            cursor.execute("TRUNCATE TABLE SentianceEventos")
            cursor.execute("TRUNCATE TABLE SdkSourceEvent")
            conn.commit()

        logger.info(f"Inserting {len(records)} records with batch commits...")
        insert_sql = "INSERT INTO SentianceEventos (sentianceid, json, tipo, created_at, app_version, is_processed) VALUES (?, ?, ?, ?, ?, 0)"

        for i, rec in enumerate(records, 1):
            cursor.execute(
                insert_sql,
                (
                    rec.get("sentianceid"),
                    rec.get("json"),
                    rec.get("tipo"),
                    rec.get("created_at"),
                    rec.get("app_version"),
                ),
            )
            if i % 500 == 0:
                conn.commit()
                logger.info(f"Committed {i} records...")

        conn.commit()

        if len(records) % 500 != 0:
            logger.info(f"Committed final {len(records) % 500} records...")

        logger.info(f"SUCCESS: Total {len(records)} records hydrated.")
        conn.close()
    except Exception as e:
        logger.error(f"CRITICAL: Hydration failed: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Hydrate local Sentiance database")
    parser.add_argument(
        "--recreate", action="store_true", help="Drop & recreate schema, then hydrate"
    )
    parser.add_argument(
        "--recreate-only",
        action="store_true",
        help="Drop & recreate schema only (no data)",
    )
    parser.add_argument(
        "--no-clear",
        action="store_true",
        help="Hydrate without clearing existing tables",
    )
    parser.add_argument(
        "--file",
        default="sample_payloads.json.gz",
        help="JSON file to hydrate (default: sample_payloads.json.gz)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of records to hydrate",
    )
    parser.add_argument(
        "--movilidad",
        action="store_true",
        help="Also recreate the local Movilidad schema (for bridge integration testing)",
    )
    args = parser.parse_args()

    if args.recreate_only:
        recreate_schema()
        if args.movilidad:
            recreate_movilidad_schema()
        logger.info("Schema(s) recreated (no data loaded).")
    elif args.recreate:
        recreate_schema()
        if args.movilidad:
            recreate_movilidad_schema()
        hydrate(args.file, clear_first=False, limit=args.limit)
    else:
        if args.movilidad:
            recreate_movilidad_schema()
        hydrate(args.file, clear_first=not args.no_clear, limit=args.limit)
