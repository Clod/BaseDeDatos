# brainstorm: ETL Refinement & Deployment

## Goal
Optimize the existing `sentiance_etl.py` script for production reliability and observability, ensuring it can be safely handed off to junior developers.

## What I already know
* The core ETL logic for all Sentiance 2026 event types is implemented.
* The script uses `pyodbc`, `gzip` compression, and `.env` for security.
* The database is SQL Server 2019 Express on AWS RDS.
* A local `uv` virtual environment is configured.

## Assumptions
* The script will run as a scheduled process (Cron or Task Scheduler).
* The current DB user has permissions to create tables or views if needed.

## Open Questions
* How should we handle persistent failures (Dead Letter Queue)?
* Do we need SQL Views for operational monitoring?
* Is an API trigger required or is polling sufficient?

## Requirements (evolving)
* [x] Externalize configuration via `.env`.
* [x] Modular handler structure.
* [x] Detailed logging and docstrings.
* [x] Implement "Error Shadow Table" (Approach B).
* [ ] Scaffold Local Development Environment (Docker + Sample Data).

## Technical Approach
1. Create `SentianceEventos_Errors` shadow table.
2. ETL logic: On failure, copy payload + traceback to shadow table and mark original as `-1`.
3. Local Env: Docker Compose for SQL Server + Data Fetching Utility for regression.


## Acceptance Criteria
* [ ] Script runs without errors on valid payloads.
* [ ] Failed records do not block the queue.
* [ ] Memory usage remains stable during large batch processing.

## Technical Notes
* Script: `sentiance_etl.py`
* Specs: `Entregable.md`, `MapeoSDK_BD.md`
* Tooling: `uv`, `pyodbc`, `dotenv`
