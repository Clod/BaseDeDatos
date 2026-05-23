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

Loads a small representative test dataset (`test_small_full.json`, ~1.3 MB). Always creates the VictaTMTK and Movilidad schemas first. Use this for day-to-day ETL development and unit testing.

```bash
cd development

# Load standard test dataset (DrivingInsights + Timeline + UserContext)
python hydrate_local_small.py

# Load an alternate dataset (e.g. only Timeline/UserContext events)
python hydrate_local_small.py --file test_context_timeline.json
```

#### `hydrate_local_db.py` — full dataset loader

Loads the full `sample_payloads.json.gz` dataset (~900 MB uncompressed, ~52 MB compressed). Use when you need production-scale data volumes or want to test specific edge cases not covered by the small dataset.

```bash
cd development

# Clear existing data and reload (default) — always clears both VictaTMTK and Movilidad
python hydrate_local_db.py

# Drop and recreate both schemas, then load data (full reset)
python hydrate_local_db.py --recreate

# Drop and recreate both schemas only (no data loaded — clean slate)
python hydrate_local_db.py --recreate-only

# Add data without clearing existing rows
python hydrate_local_db.py --no-clear

# Load only first N records
python hydrate_local_db.py --limit 500

# Load from a specific file
python hydrate_local_db.py --file my_payloads.json.gz
```

### 3. Configure `.env` for local development

Create or update `.env` in the project root. For a full local setup (VictaTMTK + Movilidad bridge), use:

```
# VictaTMTK — local Docker instance
DB_SERVER=localhost
DB_PORT=1433
DB_USER=sa
DB_PASSWORD=SentianceLocal2026!
DB_NAME=VictaTMTK

# Movilidad bridge — same Docker instance, different database
ENABLE_MOVILIDAD_BRIDGE=true
MOVILIDAD_HOST=localhost
MOVILIDAD_PORT=1433
MOVILIDAD_DATABASE=Movilidad
MOVILIDAD_USER=sa
MOVILIDAD_PASSWORD=SentianceLocal2026!
```

> **Important:** if `ENABLE_MOVILIDAD_BRIDGE` is missing or not `true`, the bridge is silently
> disabled. Movilidad will be empty even after a successful ETL run.

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

Projects processed trips from VictaTMTK into the legacy Movilidad schema at the end of each ETL batch. Gated by `ENABLE_MOVILIDAD_BRIDGE`; designed to be removed once Operaciones implements its own pipeline.

The bridge is entirely self-contained in `etl/movilidad_bridge.py`. If the Movilidad host is unreachable, the bridge logs a warning and the ETL continues normally — it never breaks the main pipeline.

### Tables populated

| Movilidad table | Source in VictaTMTK |
|-----------------|---------------------|
| `Transporte` | `Trip` |
| `Recorridos` | `Trip.waypoints_json` |
| `PuntajesPrirmariosTr` | `DrivingInsightsTrip` |
| `PuntajesSecundariosTr` | `DrivingInsightsTrip` + `DrivingInsightsHarshEvent` |
| `Conduccion` | `Trip.occupant_role` |
| `Eventos` | All child event tables |
| `EventosSignificantes` | Mirror of `Eventos` (significant events only) |
| `PerfilDeUsuario` | `UserContextHeader` (latest snapshot per user) |
| `ChoqueDeVehiculo` | `VehicleCrashEvent` |

### When does the bridge run?

The bridge fires **automatically** at the end of each ETL batch, but only when the batch
processed at least one new `DrivingInsights` event. This means:

- If you run the ETL on a fresh queue → bridge syncs those trips automatically.
- If you run the ETL on a queue that was **already processed** → `_dirty_transport_ids` is
  empty → bridge is not called → Movilidad stays empty.
- If `ENABLE_MOVILIDAD_BRIDGE` is not `true` in `.env` → bridge is disabled entirely.

### `.env` for production (AWS RDS → Movilidad on-prem)

```
ENABLE_MOVILIDAD_BRIDGE=true
MOVILIDAD_HOST=AROCLNDSQL-DEV.ikeasistencia.com.ar
MOVILIDAD_PORT=1533
MOVILIDAD_DATABASE=Movilidad
MOVILIDAD_USER=<user>
MOVILIDAD_PASSWORD=<password>
```

### `.env` for local development (Docker)

```
ENABLE_MOVILIDAD_BRIDGE=true
MOVILIDAD_HOST=localhost
MOVILIDAD_PORT=1433
MOVILIDAD_DATABASE=Movilidad
MOVILIDAD_USER=sa
MOVILIDAD_PASSWORD=SentianceLocal2026!
```

---

## Processing Everything, Including Movilidad

### Complete local workflow from scratch

```bash
# 1. Start Docker
cd development && docker-compose up -d && cd ..

# 2. Create schemas and load test data
python development/hydrate_local_small.py

# 3. Ensure .env has both VictaTMTK and Movilidad settings (see above)

# 4. Run the ETL — bridge fires automatically at the end of the batch
python etl/sentiance_etl.py

# 5. Verify Movilidad was populated
```

After step 4, all these Movilidad tables should have data:
`Transporte`, `Recorridos`, `PuntajesPrirmariosTr`, `PuntajesSecundariosTr`,
`Conduccion`, `Eventos`, `EventosSignificantes`.

### Verify Movilidad data (via MCP or any SQL client)

```sql
SELECT 'Transporte'          AS tabla, COUNT(*) AS filas FROM Movilidad.dbo.Transporte          UNION ALL
SELECT 'Recorridos',                   COUNT(*)          FROM Movilidad.dbo.Recorridos           UNION ALL
SELECT 'PuntajesPrirmariosTr',         COUNT(*)          FROM Movilidad.dbo.PuntajesPrirmariosTr UNION ALL
SELECT 'PuntajesSecundariosTr',        COUNT(*)          FROM Movilidad.dbo.PuntajesSecundariosTr UNION ALL
SELECT 'Conduccion',                   COUNT(*)          FROM Movilidad.dbo.Conduccion           UNION ALL
SELECT 'Eventos',                      COUNT(*)          FROM Movilidad.dbo.Eventos              UNION ALL
SELECT 'EventosSignificantes',         COUNT(*)          FROM Movilidad.dbo.EventosSignificantes;
```

---

## Reprocessing and Backfill

Use `scripts/sync_movilidad.py` in any of these situations:

- The bridge was added or enabled after the ETL already processed historical records.
- Movilidad was cleared and needs to be rebuilt from VictaTMTK data.
- You want to re-sync specific users or a date range after a schema change.
- The bridge failed mid-run and left Movilidad partially populated.

The script reads directly from the `Trip` table in VictaTMTK — it does not care whether
events in `SentianceEventos` are processed or not.

### Usage

```bash
# Sync all trips in VictaTMTK to Movilidad
python scripts/sync_movilidad.py

# Sync only trips for a specific user
python scripts/sync_movilidad.py --uid <sentiance_user_id>

# Sync only trips that started on or after a date
python scripts/sync_movilidad.py --since 2026-05-01

# Combine filters
python scripts/sync_movilidad.py --uid abc123 --since 2026-04-01

# Preview what would be synced without writing anything
python scripts/sync_movilidad.py --dry-run

# Process in smaller chunks (default: 50 trips per batch)
python scripts/sync_movilidad.py --batch-size 20
```

### Full reset of Movilidad + resync

If you need to rebuild Movilidad from scratch (e.g. after a schema change):

```bash
# 1. Clear and recreate Movilidad schema only (leaves VictaTMTK untouched)
python development/hydrate_local_db.py --recreate-only

# 2. Resync all trips from VictaTMTK
python scripts/sync_movilidad.py
```

Or for a complete reset of both databases:

```bash
# 1. Drop and recreate both schemas, reload all test data
python development/hydrate_local_db.py --recreate

# 2. Run ETL — bridge fires automatically
python etl/run_full_pipeline.py
```

### Why is Movilidad still empty after running the ETL?

**Check 1: Is the bridge enabled?**

The `.env` must contain `ENABLE_MOVILIDAD_BRIDGE=true`. If that variable is absent or set to
any other value, the bridge is silently skipped. The ETL log will print:
```
MovilidadBridge: desactivado (ENABLE_MOVILIDAD_BRIDGE != true)
```

**Check 2: Were the events already processed?**

The bridge only runs when the current ETL batch processed new `DrivingInsights` events.
If all events in `SentianceEventos` have `is_processed = 1`, the ETL exits early (nothing
to do) and the bridge is never called. Check with:

```sql
SELECT tipo, COUNT(*) AS total, SUM(CAST(is_processed AS INT)) AS processed
FROM VictaTMTK.dbo.SentianceEventos
GROUP BY tipo
ORDER BY tipo;
```

If `DrivingInsights` rows are all processed, use `sync_movilidad.py` to backfill.

**Check 3: Is the Movilidad connection correct?**

If the bridge is enabled but the host is wrong or the Docker container is not running, the
bridge logs a warning and continues silently. Run `scripts/sync_movilidad.py` manually —
it will raise a clear error if the connection fails.

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
