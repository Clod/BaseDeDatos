#!/usr/bin/env python3
"""
Hydrates local SQL Server with small test dataset for ETL testing.

DESCRIPTION:
    Loads test dataset from a JSON file (defaults to test_small_full.json).

USAGE:
    python hydrate_local_small.py
    python hydrate_local_small.py --file test_context_timeline.json
"""

import argparse
import json
import logging
import pyodbc

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def get_connection(autocommit=False):
    server, database, username, password = (
        "localhost",
        "VictaTMTK",
        "sa",
        "SentianceLocal2026!",
    )
    conn_str = f"DRIVER={{ODBC Driver 18 for SQL Server}};SERVER={server};DATABASE={database};UID={username};PWD={password};Encrypt=yes;TrustServerCertificate=yes"
    return pyodbc.connect(conn_str, autocommit=autocommit)


def get_master_connection():
    server, username, password = "localhost", "sa", "SentianceLocal2026!"
    conn_str = f"DRIVER={{ODBC Driver 18 for SQL Server}};SERVER={server};DATABASE=master;UID={username};PWD={password};Encrypt=yes;TrustServerCertificate=yes"
    return pyodbc.connect(conn_str, autocommit=True)


def drop_database():
    logger.info("Dropping database...")
    conn = get_master_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DROP DATABASE IF EXISTS VictaTMTK")
        conn.commit()
    finally:
        conn.close()
    logger.info("Database dropped (skipped - keeping existing data)")


def create_schema():
    logger.info("Creating schema...")
    # Connect to master to create database first (if not exists)
    conn = get_master_connection()
    cursor = conn.cursor()
    cursor.execute(
        "IF NOT EXISTS (SELECT * FROM sys.databases WHERE name = 'VictaTMTK') CREATE DATABASE VictaTMTK"
    )
    conn.commit()
    conn.close()

    # Now connect to database and create schema
    conn = get_connection()
    cursor = conn.cursor()
    with open("sql/init_db.sql", "r") as f:
        schema = f.read()
    for stmt in schema.split("GO"):
        if stmt.strip():
            cursor.execute(stmt)
    conn.commit()
    conn.close()
    logger.info("Schema created")


def hydrate(json_file: str):
    logger.info(f"Loading test data from {json_file}...")
    with open(json_file, "r") as f:
        records = json.load(f)

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SET IDENTITY_INSERT SentianceEventos ON")

    inserted = 0
    skipped = 0
    for r in records:
        if r.get("table") == "SentianceEventos":
            # Check if ID exists
            cursor.execute(
                "SELECT COUNT(*) FROM SentianceEventos WHERE id = ?", (r["id"],)
            )
            if cursor.fetchone()[0] > 0:
                skipped += 1
                continue
            cursor.execute(
                "INSERT INTO SentianceEventos (id, sentianceid, json, tipo, created_at, app_version, is_processed) VALUES (?, ?, ?, ?, GETDATE(), ?, 0)",
                (
                    r["id"],
                    r.get("sentianceid", "unknown"),
                    r["json"],
                    r["tipo"],
                    "1.1.17-test",
                ),
            )
            inserted += 1

    cursor.execute("SET IDENTITY_INSERT SentianceEventos OFF")
    conn.commit()
    conn.close()
    logger.info(f"Loaded {inserted} records, skipped {skipped} duplicates")


def main():
    parser = argparse.ArgumentParser(description="Hydrate local SQL Server with test data")
    parser.add_argument("--file", default="test_small_full.json", help="JSON test data file to load")
    args = parser.parse_args()
    hydrate(args.file)
    logger.info("SUCCESS: Test dataset loaded")


if __name__ == "__main__":
    main()
