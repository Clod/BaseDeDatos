"""
Local Database Bootstrapper - Development Utility
================================================

DESCRIPTION:
This script initializes the local SQL Server (Docker/Azure SQL Edge) by 
executing the primary 'init_db.sql' schema definition.

WHY THIS SCRIPT EXISTS:
Standard SQL Server Docker images sometimes lack pre-installed CLI tools 
(sqlcmd) or behave differently on ARM64 architectures. This Python-based 
approach provides a reliable, platform-independent way to:
1. Wait for the local container to finish booting.
2. Create the target database (VictaTMTK).
3. Apply the full relational schema.

WORKFLOW:
1. Connects to the local 'master' system database.
2. Loads 'sql/init_db.sql'.
3. Parses and executes the script in 'batches' (splitting by the 'GO' command).

AUTHOR: Claudio Grasso / AI Assistant
DATE: April 2026
"""

import pyodbc
import os
import time
import logging

# Configure logging for clear developer feedback
logging.basicConfig(
    level=logging.INFO, 
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("DB-Bootstrap")


def run_init_script():
    """
    Connects to the local Docker SQL instance, creates the database, 
    and applies the schema batches from init_db.sql.
    """
    # Local connection details for Docker sandbox
    # These credentials match the ones defined in docker-compose.yml
    server = "localhost"
    database = "master"  # Initially connect to 'master' to ensure we can CREATE DATABASE
    username = "sa"
    password = "SentianceLocal2026!"

    # Connection string using ODBC Driver 18
    # TrustServerCertificate=yes is required for local dev environments with self-signed certs.
    conn_str = (
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"SERVER={server};"
        f"DATABASE={database};"
        f"UID={username};"
        f"PWD={password};"
        f"Encrypt=yes;"
        f"TrustServerCertificate=yes"
    )

    # 1. RETRY LOOP: Wait for the Docker container to be ready
    # Databases usually take 10-20 seconds to start accepting connections.
    max_retries = 10
    conn = None
    for i in range(max_retries):
        try:
            logger.info(f"Attempting to connect to local SQL Server (Attempt {i + 1}/{max_retries})...")
            # autocommit=True is required for DDL commands like CREATE DATABASE
            conn = pyodbc.connect(conn_str, autocommit=True)
            logger.info("Connection established to local instance.")
            break
        except Exception as e:
            if i == max_retries - 1:
                logger.error(f"CRITICAL: Could not connect to local DB after {max_retries} attempts: {e}")
                return
            logger.warning("DB engine is still starting up, waiting 5 seconds...")
            time.sleep(5)

    try:
        # 2. LOAD SCHEMA FILE
        script_path = os.path.join(os.path.dirname(__file__), "sql", "init_db.sql")
        if not os.path.exists(script_path):
            logger.error(f"Schema file not found at: {script_path}")
            return

        logger.info(f"Reading schema definition from {script_path}...")
        with open(script_path, "r") as f:
            sql_script = f.read()

        # 3. PARSE BATCHES
        # T-SQL scripts use 'GO' as a separator for independent execution blocks.
        # Python's ODBC driver cannot process 'GO' directly, so we split the script manually.
        batches = sql_script.split("GO")
        
        cursor = conn.cursor()

        logger.info(f"Processing {len(batches)} schema batches...")
        for batch in batches:
            clean_batch = batch.strip()
            if clean_batch:
                try:
                    # Execute each T-SQL block individually
                    cursor.execute(clean_batch)
                    logger.info("Batch executed successfully.")
                except Exception as e:
                    # Ignore "Already exists" errors as they are expected during re-initialization
                    if "already exists" in str(e).lower():
                        logger.debug(f"Skipping (Already Exists): {str(e).split(']')[-1].strip()}")
                    else:
                        logger.error(f"Error in batch execution: {e}")

        logger.info("SUCCESS: Local Database Bootstrap Completed!")
        logger.info("You can now connect to the 'VictaTMTK' database on localhost,1433.")
        conn.close()

    except Exception as e:
        logger.error(f"Unexpected failure during bootstrap process: {e}")


if __name__ == "__main__":
    try:
        run_init_script()
    except KeyboardInterrupt:
        logger.info("Bootstrap aborted by user.")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
