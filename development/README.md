# VictaTMTK - Local Development Environment

This directory contains the infrastructure to run a local SQL Server instance for ETL development and regression testing.  
**Note:** This setup uses **Azure SQL Edge**, which is optimized for Apple Silicon (M1/M2/M3) and ARM64 architectures.

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running.
- Apple Silicon (Mac) or ARM64 Linux host.
- [uv](https://github.com/astral-sh/uv) or `pip` to install Python dependencies.

## Getting Started

### 1. Spin up SQL Server

From this directory, run:

```bash
docker-compose up -d
```

### 2. Initialize the Schema

Since MSSQL on Docker doesn't automatically run scripts on startup, and some ARM64 images lack internal tools, use the provided Python bootstrapper:

```bash
# Ensure your venv is active
source ../.venv/bin/activate

# Run the bootstrapper
python bootstrap_local_db.py
```

### 3. Connection Details

- **Host:** `localhost`
- **Port:** `1433`
- **User:** `sa`
- **Password:** `SentianceLocal2026!`
- **Database:** `VictaTMTK`

## Local Development Workflow

1. **Hydrate:** Use the `fetch_sample_data.py` (to be created) to pull real data from RDS.
2. **Develop:** Update `.env` to point to `localhost,1433`.
3. **Test:** Run `python sentiance_etl.py` and verify the results in the local tables.
4. **Reset:** If you want a fresh start, run `docker-compose down -v` to delete all data and start over.

Para hacer una prueba desde 0 (con la Base de datos limpia y con una cantidad de SentianceEventos mínima pero representativa)

Borrar la base de datos y recrearla vacía.

```python
    python hydrate_local_db.py --recreate-only   # Drop & recreate schema only
```

Cargar los dos sets de datos: 

- DrivingInsights y DrivingInsights*Event (74 registros)
- TimeLine y UserContext (9 registros)

```python
    python hydrate_local_small.py
    python hydrate_local_small.py --file test_context_timeline.json
```

Para hacer una corrida:

```python
    python  sentiance_etl.py
```

Para revisar a mano los resultados:

```python
    marimo run sentiance_inspector.py
```

## Schema Changes

### Trip table — source traceability (added 2026-04-25)

Two `BIGINT NULL` columns were added to `Trip` to track which `SdkSourceEvent` row was responsible for creating and last updating each trip:

| Column | Type | FK | Description |
|---|---|---|---|
| `creating_sdk_source_event_id` | `BIGINT NULL` | `SdkSourceEvent` | Set once on INSERT — the event that first discovered this trip |
| `last_updated_by_sdk_source_event_id` | `BIGINT NULL` | `SdkSourceEvent` | Updated on every MERGE — the last event that refreshed trip data |

To apply to an existing database without a full recreate:

```sql
ALTER TABLE Trip
    ADD creating_sdk_source_event_id BIGINT NULL
            REFERENCES SdkSourceEvent(sdk_source_event_id),
        last_updated_by_sdk_source_event_id BIGINT NULL
            REFERENCES SdkSourceEvent(sdk_source_event_id);
```

### ETL behaviour changes (2026-04-25)

- **Provisional trips are no longer written to `Trip`.**  
  `upsert_trip` now returns `None` immediately if `isProvisional = true`.  
  A trip is only stored once Sentiance marks it as final (`isProvisional = false`).

- **Trip Sync validation rule in the inspector:**  
  For each `IN_TRANSPORT` event in a `UserContextUpdate` or `requestUserContext` payload:
  - `isProvisional = false` → trip **must** exist in `Trip` (✅ if found, ❌ if missing)
  - `isProvisional = true` → trip **must not** exist in `Trip` (✅ if absent, ❌ if present)