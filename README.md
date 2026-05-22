# BaseDeDatos — Sentiance SDK ETL Pipeline

ETL pipeline that processes Sentiance SDK webhook payloads delivered via AWS IoT MQTT and loads them into a SQL Server relational model (VictaTMTK). Handles driving insights, timeline events, user context, crash detection, and SDK status for the VictaTMTK product.

---

## Architecture

```
Mobile App (Sentiance SDK)
        │  MQTT / AWS IoT Core
        ▼
SentianceEventos        ← raw payload queue (SQL Server)
        │
        ▼
etl/sentiance_etl.py    ← main ETL engine
  ├─ DrivingInsights     → Trip, DrivingInsightsTrip
  ├─ Harsh/Phone/Call/Speeding/WrongWay events → child event tables
  ├─ UserContext         → UserContextHeader + 6 child tables
  ├─ TimelineEvents      → TimelineEventHistory
  ├─ VehicleCrash        → VehicleCrashEvent
  └─ SDKStatus           → SdkStatusHistory
        │
        │  optional (ENABLE_MOVILIDAD_BRIDGE=true)
        ▼
etl/movilidad_bridge.py → Movilidad legacy schema
```

---

## Project Structure

```
etl/                        Production ETL code
  sentiance_etl.py          Main engine — reads SentianceEventos, writes domain tables
  run_full_pipeline.py      Orchestrator — loops until queue is empty
  movilidad_bridge.py       Temporary bridge to Movilidad legacy schema

scripts/
  sync_movilidad.py         Backfill utility — syncs existing trips to Movilidad

development/                Local development tooling
  docker-compose.yml        Local SQL Server (Azure SQL Edge, ARM64-compatible)
  hydrate_local_db.py       Load large payload dataset into local DB
  hydrate_local_small.py    Load small curated test dataset (fast, recommended)
  sentiance_inspector.py    Marimo visual dashboard for ETL validation
  run_inspector_batch.py    Headless batch validator (CI-friendly)
  sql/init_db.sql           VictaTMTK schema DDL
  sql/init_movilidad.sql    Movilidad local schema DDL

tests/                      Unit test suite (114 tests, no DB required)
Documentos/                 Reference docs and data dictionaries
  DiccionarioDatos.md       Complete VictaTMTK data dictionary
  analisis_mapeo_movilidad.md  Movilidad ↔ SDK field mapping analysis
  schemas.json              Movilidad schema reference (production export)
```

---

## Setup

### Prerequisites

- Python 3.10+
- `brew install unixodbc` (macOS)
- [Microsoft ODBC Driver 18 for SQL Server](https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server)
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (for local DB)
- `uv` (recommended) or `pip`

### Install Python dependencies

```bash
uv pip install --python .venv/bin/python -r requirements.txt
```

### Configure `.env`

```
DB_SERVER=<host>
DB_PORT=<port>
DB_USER=<user>
DB_PASSWORD=<password>
DB_NAME=VictaTMTK
```

Copy `.env.rds` as a starting point for production, or use the local credentials below for development.

---

## Running the ETL

### Single batch (up to 1000 records)

Processes one batch from `SentianceEventos` and exits. Useful for testing.

```bash
python etl/sentiance_etl.py
```

### Continuous pipeline (runs until queue is empty)

Loops until all `is_processed = 0` records are handled. Use this in production or for bulk historical loads.

```bash
python etl/run_full_pipeline.py
```

---

## Local Development Workflow

### 1. Start local SQL Server

```bash
cd development && docker-compose up -d
```

Local connection: `localhost:1433 / sa / SentianceLocal2026!`

### 2. Load test data

Two hydration scripts are available depending on your needs:

#### `hydrate_local_small.py` — fast, curated dataset (recommended for development)

Loads a small representative test dataset (`test_small_full.json`, ~1.3 MB). Always creates the schema first. Use this for day-to-day ETL development and unit testing.

```bash
cd development

# Load standard test dataset (DrivingInsights + Timeline + UserContext)
python hydrate_local_small.py

# Also initialize the local Movilidad schema (required to test the bridge)
python hydrate_local_small.py --setup-movilidad

# Load an alternate dataset (e.g. only Timeline/UserContext events)
python hydrate_local_small.py --file test_context_timeline.json
```

#### `hydrate_local_db.py` — full dataset loader

Loads the full `sample_payloads.json.gz` dataset (~900 MB uncompressed, ~52 MB compressed). Use when you need production-scale data volumes or want to test specific edge cases not covered by the small dataset.

```bash
cd development

# Clear existing data and reload (default)
python hydrate_local_db.py

# Drop and recreate schema, then load data (full reset)
python hydrate_local_db.py --recreate

# Drop and recreate schema only (no data loaded — clean slate)
python hydrate_local_db.py --recreate-only

# Recreate both VictaTMTK and local Movilidad schemas
python hydrate_local_db.py --recreate-only --movilidad

# Add data without clearing existing rows
python hydrate_local_db.py --no-clear

# Load only first N records
python hydrate_local_db.py --limit 500

# Load from a specific file
python hydrate_local_db.py --file my_payloads.json.gz
```

### 3. Update `.env` to point to local DB

```
DB_SERVER=localhost
DB_PORT=1433
DB_USER=sa
DB_PASSWORD=SentianceLocal2026!
DB_NAME=VictaTMTK
```

### 4. Run the ETL locally

```bash
python etl/sentiance_etl.py
```

### 5. Validate results with the inspector

```bash
# Interactive visual dashboard
.venv/bin/marimo run development/sentiance_inspector.py

# Headless batch validator (outputs pass/fail per record)
python development/run_inspector_batch.py
```

---

## Movilidad Bridge (Temporary)

Projects processed trips from VictaTMTK into the legacy Movilidad schema at the end of each ETL batch. Gated by an env flag; designed to be removed once Operaciones implements its own pipeline.

### Activate

Add to `.env`:

```
ENABLE_MOVILIDAD_BRIDGE=true
MOVILIDAD_HOST=<host>
MOVILIDAD_PORT=<port>
MOVILIDAD_DATABASE=Movilidad
MOVILIDAD_USER=<user>
MOVILIDAD_PASSWORD=<password>
```

### Backfill already-processed trips

Use when the bridge was activated after the ETL had already processed historical records:

```bash
python scripts/sync_movilidad.py                    # all trips
python scripts/sync_movilidad.py --uid <user_id>    # one user
python scripts/sync_movilidad.py --since 2026-05-01 # from a date
python scripts/sync_movilidad.py --dry-run          # preview only
```

See `Documentos/analisis_mapeo_movilidad.md` § 10 for removal instructions.

---

## Tests

```bash
.venv/bin/pytest tests/ -q
```

All tests are pure-unit (no database required). Covers ETL routing, timestamp formatting, GZIP compression, SHA-256 hashing, SQL parameter extraction, and the Movilidad bridge.

---

## Further Reading

- `CLAUDE.md` — MCP server configuration, full VictaTMTK schema reference, AI assistant context
- `Documentos/DiccionarioDatos.md` — complete data dictionary for all 23 tables
- `Documentos/analisis_mapeo_movilidad.md` — Sentiance SDK ↔ Movilidad field mapping
- `development/README.md` — Docker setup and local SQL Server details
