import pyodbc
import os
import time
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("DB-Bootstrap")


def run_init_script():
    # Local connection details for Docker
    server = "localhost"
    database = "master"  # Connect to master first to create the DB
    username = "sa"
    password = "SentianceLocal2026!"

    conn_str = f"DRIVER={{ODBC Driver 18 for SQL Server}};SERVER={server};DATABASE={database};UID={username};PWD={password};Encrypt=yes;TrustServerCertificate=yes"

    # Wait for the DB to be ready
    max_retries = 5
    for i in range(max_retries):
        try:
            logger.info(
                f"Attempting to connect to local SQL Server (Attempt {i + 1}/{max_retries})..."
            )
            conn = pyodbc.connect(conn_str, autocommit=True)
            logger.info("Connected to local SQL Server.")
            break
        except Exception as e:
            if i == max_retries - 1:
                logger.error(f"Could not connect to local DB: {e}")
                return
            logger.warning("DB not ready yet, waiting 5 seconds...")
            time.sleep(5)

    try:
        # Read the SQL file
        script_path = os.path.join(os.path.dirname(__file__), "sql", "init_db.sql")
        with open(script_path, "r") as f:
            sql_script = f.read()

        # SQL Server scripts often use 'GO' as a batch separator.
        # pyodbc cannot execute 'GO', so we must split the script manually.
        batches = sql_script.split("GO")

        cursor = conn.cursor()

        logger.info("Executing initialization script batches...")
        for batch in batches:
            clean_batch = batch.strip()
            if clean_batch:
                try:
                    cursor.execute(clean_batch)
                    logger.info("Batch executed successfully.")
                except Exception as e:
                    # Some errors (like "Database already exists") might be expected
                    if "already exists" in str(e):
                        logger.debug(f"Skipping: {str(e).split(']')[-1].strip()}")
                    else:
                        logger.error(f"Error in batch: {e}")

        logger.info("Local Database Bootstrap Completed Successfully!")
        conn.close()

    except Exception as e:
        logger.error(f"Bootstrap failed: {e}")


if __name__ == "__main__":
    run_init_script()
