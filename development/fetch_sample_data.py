"""
Sentiance Data Extractor - Development Utility
=============================================

DESCRIPTION:
This script retrieves real-world Sentiance SDK payloads from the production
AWS RDS instance and saves them directly to a compressed GZIP JSON file.
"""

import os
import json
import pyodbc
import logging
import gzip
from datetime import datetime, timedelta
from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("DataFetcher")
load_dotenv(dotenv_path="../.env.rds")


def fetch_data(months=2):
    # First clear any existing env vars
    for k in ["DB_SERVER", "DB_PORT", "DB_USER", "DB_PASSWORD", "DB_NAME"]:
        if k in os.environ:
            del os.environ[k]

    load_dotenv(dotenv_path="../.env.rds", override=True)
    server = os.getenv("DB_SERVER")
    port = os.getenv("DB_PORT")
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")
    database = os.getenv("DB_NAME")

    if not all([server, port, user, password, database]):
        logger.error("Incomplete database configuration in .env.")
        return

    conn_str = (
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"SERVER={server},{port};"
        f"DATABASE={database};"
        f"UID={user};"
        f"PWD={password};"
        f"Encrypt=yes;"
        f"TrustServerCertificate=yes"
    )

    try:
        logger.info(f"Connecting to production AWS RDS: {server}...")
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()

        cutoff_date = (datetime.now() - timedelta(days=months * 30)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        logger.info(f"Fetching records since: {cutoff_date}")

        query = """
            SELECT id, sentianceid, json, tipo, created_at, app_version
            FROM SentianceEventos
            WHERE created_at >= ?
            ORDER BY created_at DESC
        """

        cursor.execute(query, (cutoff_date,))

        logger.info("Fetching rows...")
        data = []
        batch_size = 1000
        while True:
            rows = cursor.fetchmany(batch_size)
            if not rows:
                break
            for row in rows:
                data.append(
                    {
                        "original_id": row.id,
                        "sentianceid": row.sentianceid,
                        "json": row.json,
                        "tipo": row.tipo,
                        "created_at": str(row.created_at),
                        "app_version": row.app_version,
                    }
                )
            logger.info(f"Fetched {len(data)} records...")

        output_file = "sample_payloads.json.gz"
        logger.info(f"Compressing and saving {len(data)} records to '{output_file}'...")

        # Save directly to GZIP
        with gzip.open(output_file, "wt", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

        logger.info(f"SUCCESS: Exported to {output_file}")
        conn.close()

    except Exception as e:
        logger.error(f"CRITICAL: Failed to extract data: {e}")


if __name__ == "__main__":
    fetch_data(months=2)
