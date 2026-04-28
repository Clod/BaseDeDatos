# BaseDeDatos — Claude Code Project Guide

## Project Overview

ETL pipeline that processes Sentiance SDK webhook payloads (JSON) and loads them into SQL Server tables. The pipeline handles timeline events, driving insights, user context, and trip data for the VictaTMTK product.

**Main entry point:** `sentiance_etl.py`  
**Local dev tooling:** `development/` directory  
**Tests:** `tests/`

---

## MCP Database Servers

Three MCP servers are available to query databases directly from this session. All use the `mcp-node-mssql` package and expose the same tool set.

### Available tools (all three servers)

| Tool | Description |
|------|-------------|
| `mcp__<server>__query` | Execute a SQL query |
| `mcp__<server>__get-tables` | List all tables in the database |
| `mcp__<server>__get-table` | Get schema for a specific table |
| `mcp__<server>__get-stored-procedures` | List stored procedures |
| `mcp__<server>__get-stored-procedure` | Get a stored procedure definition |
| `mcp__<server>__start-transaction` | Begin a transaction |
| `mcp__<server>__commit-transaction` | Commit the current transaction |
| `mcp__<server>__rollback-transaction` | Roll back the current transaction |

---

### 1. `mssql` — Production (AWS RDS)

The primary production database hosted on Amazon RDS.

- **Host:** `ltkbase003.cjo9vciowl0y.us-east-1.rds.amazonaws.com`
- **Port:** `9433`
- **Database:** `VictaTMTK`
- **User:** `ClaudioVicta`
- **Tool prefix:** `mcp__mssql__`

**Use for:** Reading production data, validating ETL output, inspecting real Sentiance payloads already processed.  
**Caution:** This is live production data. Prefer `SELECT`-only queries; avoid writes unless intentional.

---

### 2. `mssql-local` — Local Docker Development

A local SQL Server (Azure SQL Edge) instance running via Docker Compose in `development/docker-compose.yml`. Mirrors the production schema exactly.

- **Host:** `localhost`
- **Port:** `1433`
- **Database:** `VictaTMTK`
- **User:** `sa`
- **Tool prefix:** `mcp__mssql-local__`

**Use for:** Development, regression testing, schema exploration without risk to production.  
To start: `cd development && docker-compose up -d`  
To reset: `python development/hydrate_local_db.py --recreate-only`

---

### 3. `mssql-movilidad` — Movilidad (External)

A separate SQL Server instance for the Movilidad system, hosted on an external dev server.

- **Host:** `AROCLNDSQL-DEV.ikeasistencia.com.ar`
- **Port:** `1533`
- **Database:** `Movilidad`
- **User:** `UserMovilidad`
- **Tool prefix:** `mcp__mssql-movilidad__`

**Use for:** Querying the Movilidad source system, cross-referencing data with the Sentiance pipeline.

---

## VictaTMTK Schema — Key Tables

Both `mssql` and `mssql-local` share this schema.

| Table | Description |
|-------|-------------|
| `SentianceEventos` | Raw incoming webhook payloads (source queue) |
| `SentianceEventos_Errors` | Failed processing rows |
| `SdkSourceEvent` | Parsed SDK source events |
| `Trip` | Trip records |
| `DrivingInsightsTrip` | Driving insights per trip |
| `DrivingInsightsHarshEvent` | Harsh driving events |
| `DrivingInsightsPhoneEvent` | Phone usage events |
| `DrivingInsightsCallEvent` | Call events during trips |
| `DrivingInsightsSpeedingEvent` | Speeding events |
| `DrivingInsightsWrongWayDrivingEvent` | Wrong-way driving events |
| `UserContextHeader` | User context snapshots |
| `UserContextUpdateCriteria` | Context update criteria |
| `UserHomeHistory` | Detected home locations |
| `UserWorkHistory` | Detected work locations |
| `UserContextActiveSegmentDetail` | Active segment details |
| `UserContextSegmentAttribute` | Segment attributes |
| `UserContextEventDetail` | Context event details |
| `TimelineEventHistory` | Timeline events |
| `UserActivityHistory` | User activity history |
| `UserMetadata` | User metadata |

---

## Development Notes

- Credentials for local DB are in `.env` (not committed). Production credentials live in MCP server config only.
- The ETL reads from `SentianceEventos` (unprocessed rows), transforms JSON payloads, and writes to the target tables above.
- `development/sentiance_inspector.py` is a dashboard for inspecting processed vs. pending events.
- `development/run_inspector_batch.py` runs the inspector in headless/batch mode.
# Project Context

## Knowledge Base
- All reference documentation is in `wiki/`. Always consult `wiki/` for architecture decisions, conventions, and domain knowledge.
- Do NOT read from `raw/`. That directory contains unprocessed source material and should be ignored.

## Wiki Structure
- `wiki/architecture.md` — system design
- `wiki/patterns.md` — coding conventions
