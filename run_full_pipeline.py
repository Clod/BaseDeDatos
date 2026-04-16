from sentiance_etl import SentianceETL
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("FullPipeline")

def run():
    etl = SentianceETL()
    while True:
        logger.info("Starting new batch of 1000...")
        # Modification: return rows processed to know when to stop
        # Actually, I'll just check if it finished without errors
        try:
            etl.run(batch_size=1000)
        except Exception as e:
            logger.error(f"Batch failed: {e}")
            break
        
        # Check remaining
        etl.connect()
        etl.cursor.execute("SELECT COUNT(*) FROM SentianceEventos WHERE is_processed = 0")
        remaining = etl.cursor.fetchone()[0]
        etl.close()
        
        logger.info(f"Remaining records: {remaining}")
        if remaining == 0:
            break

if __name__ == "__main__":
    run()
