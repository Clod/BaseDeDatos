"""
Local Database Hydrator - Development Utility
============================================

DESCRIPTION:
This script populates the local SQL Server (Docker) with sample Sentiance 
payloads. It supports reading directly from compressed GZIP files (.json.gz).
"""

import json
import pyodbc
import os
import logging
import gzip

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("Hydrator")

def hydrate(json_file="sample_payloads.json.gz", clear_first=True):
    server, database, username, password = "localhost", "VictaTMTK", "sa", "SentianceLocal2026!"
    conn_str = f"DRIVER={{ODBC Driver 18 for SQL Server}};SERVER={server};DATABASE={database};UID={username};PWD={password};Encrypt=yes;TrustServerCertificate=yes"

    if not os.path.exists(json_file):
        logger.error(f"Sample file '{json_file}' not found.")
        return

    logger.info(f"Opening compressed data file: {json_file}")
    try:
        # Detect if file is gzipped based on extension
        if json_file.endswith('.gz'):
            with gzip.open(json_file, 'rt', encoding='utf-8') as f:
                records = json.load(f)
        else:
            with open(json_file, 'r') as f:
                records = json.load(f)
    except Exception as e:
        logger.error(f"Failed to read data file: {e}")
        return

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
            cursor.execute(insert_sql, (rec.get("sentianceid"), rec.get("json"), rec.get("tipo"), rec.get("created_at"), rec.get("app_version")))
            if i % 500 == 0:
                conn.commit()
                logger.info(f"Committed {i} records...")
        
        conn.commit()
        logger.info(f"SUCCESS: Total {len(records)} records hydrated.")
        conn.close()
    except Exception as e:
        logger.error(f"CRITICAL: Hydration failed: {e}")

if __name__ == "__main__":
    hydrate()
