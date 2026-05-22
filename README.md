# BaseDeDatos — Sentiance SDK ETL Pipeline

ETL pipeline that processes Sentiance SDK webhook payloads delivered via AWS IoT MQTT and loads them into a SQL Server relational model (VictaTMTK). Handles driving insights, timeline events, user context, crash detection, and SDK status for the VictaTMTK product.

---

## Architecture

```
Mobile App (Sentiance SDK)
        │  MQTT / AWS IoT Core
        ▼
SentianceEventos (SQL Server — raw queue)
        │
        ▼
etl/sentiance_etl.py  ──────────────────────────────────► VictaTMTK
  ├─ process_driving_insights()   → Trip, DrivingInsightsTrip
  ├─ process_driving_insights_harsh_events()  → DrivingInsightsHarshEvent
  ├─ process_driving_insights_phone_events()  → DrivingInsightsPhoneEvent
  ├─ process_driving_insights_call_events()   → DrivingInsightsCallEvent
  ├─ process_driving_insights_speeding_events() → DrivingInsightsSpeedingEvent
  ├─ process_user_context()       → UserContextHeader + 6 child tables
  ├─ process_timeline_events()    → TimelineEventHistory
  ├─ process_crash_event()        → VehicleCrashEvent
  └─ process_sdk_status()         → SdkStatusHistory
        │
        │  (optional, via ENABLE_MOVILIDAD_BRIDGE=true)
        ▼
etl/movilidad_bridge.py ─────────────────────────────────► Movilidad (legacy)
```

---

## Quick Start

### 1. Prerequisites

- Python 3.10+
- `brew install unixodbc` + Microsoft ODBC Driver 18 for SQL Server
- `uv` (or pip) for package management

### 2. Install dependencies

```bash
uv pip install --python .venv/bin/python -r requirements.txt
```

### 3. Configure `.env`

```bash
cp .env.rds .env   # or create from scratch
```

Required variables:
```
DB_SERVER=...
DB_PORT=...
DB_USER=...
DB_PASSWORD=...
DB_NAME=VictaTMTK
```

---

## Running the ETL

### Single batch (up to 1000 records)
```bash
python etl/sentiance_etl.py
```

### Continuous pipeline (runs until queue is empty)
```bash
python etl/run_full_pipeline.py
```

### Backfill Movilidad (sync already-processed trips)
```bash
MOVILIDAD_HOST=... MOVILIDAD_PORT=... MOVILIDAD_DATABASE=Movilidad \
MOVILIDAD_USER=... MOVILIDAD_PASSWORD=... \
python scripts/sync_movilidad.py [--uid <id>] [--since 2026-01-01] [--dry-run]
```

---

## Project Structure

```
etl/                    Core ETL pipeline
  sentiance_etl.py      Main engine — routes payloads to domain tables
  run_full_pipeline.py  Orchestrator — loops until queue empty
  movilidad_bridge.py   Temporary bridge → Movilidad legacy schema

scripts/                Operational utilities
  sync_movilidad.py     Manual backfill for Movilidad tables

development/            Local dev tooling
  docker-compose.yml    Local SQL Server (Azure SQL Edge)
  hydrate_local_db.py   Load sample data into local DB
  hydrate_local_small.py  Load small test dataset
  sentiance_inspector.py  Marimo dashboard for ETL validation
  run_inspector_batch.py  Headless batch validator
  sql/init_db.sql       VictaTMTK schema
  sql/init_movilidad.sql  Movilidad local schema

tests/                  Unit test suite (114 tests)
Documentos/             Reference documentation and data dictionaries
```

---

## Tests

```bash
.venv/bin/pytest tests/ -q
```

All tests are pure-unit (no DB required). Coverage includes ETL routing, timestamp formatting, compression, hashing, parameter extraction, and the Movilidad bridge.

---

## Local Development

```bash
# Start local SQL Server
cd development && docker-compose up -d

# Initialize schemas + load test data
python development/hydrate_local_small.py --setup-movilidad

# Launch interactive inspector
.venv/bin/marimo run development/sentiance_inspector.py
```

See `CLAUDE.md` for MCP server configuration, full schema reference, and Movilidad bridge removal instructions.
