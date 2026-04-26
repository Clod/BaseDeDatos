#!/usr/bin/env python3
"""
Reset and Hydrate Minimal Database - Development Utility
========================================================

DESCRIPTION:
This script orchestrates the full reset of the local database and hydrates 
it with a minimal, representative dataset for testing.

PURPOSE/WHY:
To provide a one-click way to get a clean, minimal state for ETL development.

WORKFLOW:
1. Run hydrate_local_db.py --recreate-only (Recreate schema).
2. Run hydrate_local_small.py (Load 74 DrivingInsights records).
3. Run hydrate_local_small.py --file test_context_timeline.json (Load 9 Timeline/Context records).

USAGE:
    python reset_minimal_db.py
"""

import subprocess
import sys
import logging
import os

# Operational Logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("ResetMinimal")

def run_command(cmd_list):
    """Executes a shell command and logs its status."""
    logger.info(f"Executing: {' '.join(cmd_list)}")
    try:
        # Run using current python interpreter to ensure environment consistency
        result = subprocess.run(
            [sys.executable] + cmd_list,
            check=True,
            capture_output=True,
            text=True
        )
        for line in result.stdout.splitlines():
            logger.info(f"  [STDOUT] {line}")
    except subprocess.CalledProcessError as e:
        logger.error(f"Command failed with exit code {e.returncode}")
        logger.error(f"Error output: {e.stderr}")
        sys.exit(1)

def main():
    # Ensure we are in the development directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)

    logger.info("Starting minimal database reset...")

    # 1. Recreate schema
    run_command(["hydrate_local_db.py", "--recreate-only"])

    # 2. Load DrivingInsights dataset
    run_command(["hydrate_local_small.py"])

    # 3. Load Timeline & Context dataset
    run_command(["hydrate_local_small.py", "--file", "test_context_timeline.json"])

    logger.info("SUCCESS: Database reset and minimal hydration complete.")

if __name__ == "__main__":
    main()
