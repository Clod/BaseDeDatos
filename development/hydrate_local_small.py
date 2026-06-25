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
import os
import pyodbc
from dotenv import load_dotenv

# Load database credentials from the local .env file in the project root
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def _get_conn_str(server, port, database, username, password):
    """
    Builds a pyodbc connection string by dynamically choosing the best installed ODBC driver.
    Only adds modern encryption options if an 'ODBC Driver' (v17+) is selected.
    """
    available_drivers = pyodbc.drivers()
    driver = os.getenv("DB_DRIVER")
    if not driver:
        # Preferred drivers list
        for d in ["ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server", "SQL Server"]:
            if d in available_drivers:
                driver = d
                break
        if not driver:
            driver = "SQL Server"

    conn_str = f"DRIVER={{{driver}}};SERVER={server},{port};DATABASE={database};UID={username};PWD={password}"

    # Encrypt and TrustServerCertificate parameters are only supported by modern ODBC Driver 17+
    if "ODBC Driver" in driver:
        conn_str += ";Encrypt=yes;TrustServerCertificate=yes"

    return conn_str


def get_connection(autocommit=False):
    """
    Returns a connection to the VictaTMTK database using credentials from environment.
    """
    server = os.getenv("DB_SERVER", "localhost")
    port = os.getenv("DB_PORT", "1433")
    database = os.getenv("DB_NAME", "VictaTMTK")
    username = os.getenv("DB_USER", "sa")
    password = os.getenv("DB_PASSWORD", "SentianceLocal2026!")

    conn_str = _get_conn_str(server, port, database, username, password)
    return pyodbc.connect(conn_str, autocommit=autocommit)


def get_master_connection():
    """
    Returns a connection to the master database using credentials from environment.
    """
    server = os.getenv("DB_SERVER", "localhost")
    port = os.getenv("DB_PORT", "1433")
    username = os.getenv("DB_USER", "sa")
    password = os.getenv("DB_PASSWORD", "SentianceLocal2026!")

    conn_str = _get_conn_str(server, port, "master", username, password)
    return pyodbc.connect(conn_str, autocommit=True)


def drop_database():
    logger.info("Dropping database...")
    db_name = os.getenv("DB_NAME", "VictaTMTK")
    conn = get_master_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(f"DROP DATABASE IF EXISTS {db_name}")
        conn.commit()
    finally:
        conn.close()
    logger.info("Database dropped (skipped - keeping existing data)")


def _run_sql_file(cursor, sql_file: str):
    """Executes a SQL file against an already-open autocommit cursor, splitting on GO."""
    import os
    script_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(script_dir, "sql", sql_file)
    with open(path, "r") as f:
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


def create_schema():
    db_name = os.getenv("DB_NAME", "VictaTMTK")
    logger.info(f"Creating {db_name} schema...")
    conn = get_master_connection()
    cursor = conn.cursor()
    cursor.execute(
        f"IF NOT EXISTS (SELECT * FROM sys.databases WHERE name = '{db_name}') CREATE DATABASE {db_name}"
    )
    _run_sql_file(cursor, "init_db.sql")
    conn.close()
    logger.info(f"{db_name} schema ready")


def create_movilidad_schema():
    db_name = os.getenv("MOVILIDAD_DATABASE", "Movilidad")
    logger.info(f"Creating local {db_name} schema...")
    conn = get_master_connection()
    cursor = conn.cursor()
    _run_sql_file(cursor, "init_movilidad.sql")
    conn.close()
    logger.info(f"{db_name} schema ready")


def clear_movilidad():
    server = os.getenv("MOVILIDAD_HOST", os.getenv("DB_SERVER", "localhost"))
    port = os.getenv("MOVILIDAD_PORT", os.getenv("DB_PORT", "1433"))
    database = os.getenv("MOVILIDAD_DATABASE", "Movilidad")
    username = os.getenv("MOVILIDAD_USER", os.getenv("DB_USER", "sa"))
    password = os.getenv("MOVILIDAD_PASSWORD", os.getenv("DB_PASSWORD", "SentianceLocal2026!"))

    conn_str = _get_conn_str(server, port, database, username, password)
    try:
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        logger.info("Clearing Movilidad tables...")
        for table in [
            "ChoqueDeVehiculo", "PerfilDeUsuario", "EventosSignificantes",
            "Eventos", "PuntajesSecundariosTr", "PuntajesPrirmariosTr",
            "Recorridos", "Conduccion", "Transporte", "Puntajes",
        ]:
            cursor.execute(f"DELETE FROM {table}")
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"Could not clear Movilidad (may not exist yet): {e}")


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
    _default_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_small_full.json")
    parser.add_argument("--file", default=_default_file, help="JSON test data file to load")
    args = parser.parse_args()
    create_schema()
    create_movilidad_schema()
    clear_movilidad()
    hydrate(args.file)
    logger.info("SUCCESS: Test dataset loaded")


if __name__ == "__main__":
    main()
