"""
Sentiance ETL Batch Runner - Operations Utility
==============================================

DESCRIPTION:
This script acts as the orchestration layer for the SentianceETL engine.
While the core ETL script (sentiance_etl.py) processes a single batch, 
this utility provides a continuous execution loop to clear the entire 
landing zone queue.

PURPOSE:
- To automate the processing of large volumes of historical data.
- To provide operational monitoring (remaining records count) during execution.
- To ensure the pipeline continues running until 'is_processed = 0' is empty.

WORKFLOW:
1. Instantiates the SentianceETL engine.
2. Enters a loop that calls etl.run() with a large batch size.
3. Queries the database to report progress (remaining count).
4. Terminates automatically when the work queue is empty.

USAGE:
python run_full_pipeline.py

AUTHOR: Claudio Grasso / AI Assistant
DATE: April 2026
"""

from sentiance_etl import SentianceETL
import logging

# Configure logging for operational visibility
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("FullPipeline")

def run():
    """
    Main orchestration loop. Continues processing batches until the queue is empty.
    """
    logger.info("Starting Full Pipeline Orchestration...")
    etl = SentianceETL()
    
    batch_count = 0
    while True:
        batch_count += 1
        logger.info(f"--- Starting Batch #{batch_count} ---")
        
        try:
            # Process a large chunk of records
            has_data = etl.run(batch_size=1000)
            
            # If the run method returns False (no more data), we terminate
            if not has_data:
                logger.info("Queue is empty. Orchestration finished successfully.")
                break
                
        except Exception as e:
            logger.error(f"Batch #{batch_count} encountered a fatal error: {e}")
            logger.info("Retrying next batch after fatal error...")
            continue
        
        # Operational check: How much work is left?
        try:
            etl.connect()
            etl.cursor.execute("SELECT COUNT(*) FROM SentianceEventos WHERE is_processed = 0")
            remaining = etl.cursor.fetchone()[0]
            etl.close()
            logger.info(f"Progress Report: {remaining} records remaining in queue.")
        except:
            logger.warning("Could not retrieve progress count, continuing...")

if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        logger.info("Orchestration interrupted by user.")
