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
