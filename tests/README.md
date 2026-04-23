# Test Suite — `sentiance_etl.py`

> **94 unit tests, no database required, runs in ~0.2 seconds.**

This directory contains the unit test suite for `sentiance_etl.py`. Tests are
designed to be fast, isolated, and runnable without any database or `.env` file.

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Directory Structure](#directory-structure)
3. [How Tests Work (No DB Required)](#how-tests-work-no-db-required)
4. [Running Tests](#running-tests)
5. [Test Files Reference](#test-files-reference)
6. [Fixtures Reference](#fixtures-reference)
7. [Writing New Tests](#writing-new-tests)
8. [Understanding the Mock Chain](#understanding-the-mock-chain)
9. [Bugs Found by These Tests](#bugs-found-by-these-tests)
10. [Future: Regression Tests](#future-regression-tests)

---

## Quick Start

```bash
# From the project root
.venv/bin/python3 -m pytest tests/unit/ -v
```

That's it. No `.env`, no Docker, no SQL Server.

---

## Directory Structure

```
tests/
├── README.md               ← You are here
├── __init__.py             ← Makes tests/ a Python package
├── conftest.py             ← Shared fixtures (etl, mock_cursor, etl_with_cursor)
├── pytest.ini              ← pytest configuration (in project root, not here)
└── unit/
    ├── __init__.py
    ├── test_format_ts.py       ← Phase 1: timestamp formatting
    ├── test_compress.py        ← Phase 1: GZIP compression round-trips
    ├── test_hash.py            ← Phase 1: SHA-256 deduplication hashing
    ├── test_param_extraction.py ← Phase 2: SQL parameter extraction per handler
    └── test_event_routing.py   ← Phase 2: tipo → process_* dispatch + orphan guard
```

---

## How Tests Work (No DB Required)

`SentianceETL.__init__()` reads environment variables and builds a connection
string. Normally it would raise `ValueError` if the `.env` file is missing.

The `conftest.py` **patches `os.getenv`** before instantiating the class, so
the constructor sees fake-but-valid-looking values:

```python
_FAKE_ENV = {
    "DB_SERVER": "localhost",
    "DB_PORT":   "1433",
    "DB_USER":   "sa",
    "DB_PASSWORD": "test",
    "DB_NAME":   "VictaTMTK",
}
```

The instance is created but **never connected** (`connect()` is never called).
All DB interactions in Phase 2 tests go through a `MagicMock` cursor.

---

## Running Tests

### Run everything

```bash
.venv/bin/python3 -m pytest tests/unit/
```

### Run with verbose output (recommended)

```bash
.venv/bin/python3 -m pytest tests/unit/ -v
```

### Run a single test file

```bash
.venv/bin/python3 -m pytest tests/unit/test_format_ts.py -v
```

### Run a single test class

```bash
.venv/bin/python3 -m pytest tests/unit/test_format_ts.py::TestFormatTsTruncation -v
```

### Run a single test by name

```bash
.venv/bin/python3 -m pytest tests/unit/test_format_ts.py::TestFormatTsTruncation::test_sub_millisecond_is_truncated_to_23_chars -v
```

### Run only tests matching a keyword

```bash
# Run all tests with "orphan" in their name
.venv/bin/python3 -m pytest tests/unit/ -k "orphan" -v

# Run all tests with "compress" or "hash" in their name
.venv/bin/python3 -m pytest tests/unit/ -k "compress or hash" -v
```

### Run and stop at first failure

```bash
.venv/bin/python3 -m pytest tests/unit/ -x
```

### Show local variable values on failure (more detail)

```bash
.venv/bin/python3 -m pytest tests/unit/ -v --tb=long
```

### Run quietly (just the summary line)

```bash
.venv/bin/python3 -m pytest tests/unit/ -q
```

---

## Test Files Reference

### `test_format_ts.py` — Timestamp Formatting (14 tests)

Tests `SentianceETL.format_ts()`, which converts ISO-8601 SDK timestamps to
SQL Server `DATETIME2(3)` format.

**Key rules being verified:**
- `"2026-04-01T14:30:00.123Z"` → `"2026-04-01 14:30:00.123"` (`T`→space, no `Z`)
- Output is **hard-truncated at 23 characters** (3 decimal places max)
- `None`, `""`, `0` all return `None` (SQL `NULL`)
- Output never contains `T` or ends with `Z`

```bash
.venv/bin/python3 -m pytest tests/unit/test_format_ts.py -v
```

---

### `test_compress.py` — GZIP Compression (10 tests)

Tests `SentianceETL.compress_data()`, which GZIP-compresses JSON for storage
in `VARBINARY(MAX)` columns (`waypoints_json`, `transport_tags_json`, etc.).

**Key rules being verified:**
- Output is `bytes` (pyodbc-compatible)
- Decompressing the output and parsing JSON equals the original Python object
- Large payloads are actually smaller after compression
- `None`, `[]`, `{}`, `0`, `False` all return `None` (SQL `NULL`)

```bash
.venv/bin/python3 -m pytest tests/unit/test_compress.py -v
```

---

### `test_hash.py` — SHA-256 Deduplication (9 tests)

Tests `SentianceETL.get_hash()`, which generates a SHA-256 fingerprint of the
raw JSON string for the `SdkSourceEvent.payload_hash` column.

**Key rules being verified:**
- Same input always produces the same 64-char lowercase hex string
- Any change to content (even whitespace) produces a different hash
- Output length ≤ 64 (fits in `VARCHAR(64)`)
- Cross-validated against Python's stdlib `hashlib.sha256`

```bash
.venv/bin/python3 -m pytest tests/unit/test_hash.py -v
```

---

### `test_param_extraction.py` — SQL Parameter Extraction (26 tests)

Tests that each `process_*` handler correctly reads the right fields from the
JSON payload and passes them to `cursor.execute()` in the right order and type.

Uses the `etl_with_cursor` fixture: a real ETL instance connected to a
`MagicMock` cursor. After calling a handler, the test inspects which SQL
parameters were passed.

**Handlers covered:**
| Class | Handler |
|-------|---------|
| `TestProcessDrivingInsightsParams` | `process_driving_insights` |
| `TestProcessUserContextListenerParams` | `process_user_context` (Listener) |
| `TestProcessUserContextManualParams` | `process_user_context` (Manual) |
| `TestProcessCrashEventParams` | `process_crash_event` |
| `TestProcessSdkStatusParams` | `process_sdk_status` |
| `TestProcessMetadataParams` | `process_metadata` |
| `TestProcessTimelineEventsParams` | `process_timeline_events` |

```bash
.venv/bin/python3 -m pytest tests/unit/test_param_extraction.py -v
```

---

### `test_event_routing.py` — Event Dispatch + Orphan Guard (21 tests)

Tests the `run()` method's routing logic and its orphan-child protection.

**Routing tests (parametrized, 15 event types):**
Every supported `tipo` value is verified to call the correct `process_*` method.

**Orphan guard tests (4 tests):**
When a child event (`DrivingInsightsHarshEvents`, etc.) arrives before its
parent `DrivingInsights` record, it must be **skipped and left with
`is_processed=0`** for retry. If it has no `transportId` at all, it must be
marked `is_processed=-1`.

**`run()` return value tests (3 tests):**
- Returns `False` when no rows
- Returns `True` when at least one record was processed
- Returns `False` when all records in the batch are orphan children (prevents
  infinite loops in `run_full_pipeline.py`)

```bash
.venv/bin/python3 -m pytest tests/unit/test_event_routing.py -v
```

---

## Fixtures Reference

All fixtures are defined in `tests/conftest.py` and are available to all test
files automatically (pytest discovers `conftest.py` automatically).

### `etl`

A `SentianceETL` instance with `os.getenv` patched. The instance is
**not connected** to any database. Use this for Phase 1 tests of pure
functions (`format_ts`, `compress_data`, `get_hash`).

```python
def test_something(etl):
    result = etl.format_ts("2026-04-01T10:00:00Z")
    assert result == "2026-04-01 10:00:00"
```

### `mock_cursor`

A `MagicMock` that mimics a `pyodbc` cursor. Its `fetchone()` returns `(999,)`
by default (simulating `@@IDENTITY` or a `SELECT` result). You can override
this in individual tests:

```python
def test_something(mock_cursor):
    mock_cursor.fetchone.return_value = (42,)
    # ... use mock_cursor however you need
```

### `etl_with_cursor`

An `etl` instance whose `cursor` attribute is set to a `mock_cursor`.
Use this for Phase 2 tests of `process_*` methods:

```python
def test_something(etl_with_cursor):
    etl_with_cursor.process_sdk_status(sid=1, uid="u1", payload={...})
    params = etl_with_cursor.cursor.execute.call_args_list[0].args[1]
    assert params[2] == "STARTED"
```

---

## Writing New Tests

### Adding a test for a new `process_*` method

1. Add a new class to `test_param_extraction.py`
2. Use the `etl_with_cursor` fixture
3. Build a minimal realistic payload dict
4. Call the method
5. Inspect `_get_call_params(etl_with_cursor.cursor, <call_index>)`

```python
class TestProcessMyNewHandler:

    def test_my_field_extracted(self, etl_with_cursor):
        payload = {"myField": "expected_value", ...}
        etl_with_cursor.process_my_new_handler(sid=1, uid="u1", payload=payload)
        params = _get_call_params(etl_with_cursor.cursor, 0)
        assert params[3] == "expected_value"
```

### Adding a test for a new `tipo` in the routing table

Add a new entry to the `@pytest.mark.parametrize` list in
`TestEventRouting.test_tipo_dispatches_to_correct_handler`:

```python
("MyNewEventType", "process_my_new_handler"),
```

And add the mock to the `routed_etl` fixture:

```python
etl.process_my_new_handler = MagicMock()
```

### How to find which `execute()` call to inspect

Each `process_*` method makes multiple `cursor.execute()` calls (one per
INSERT/SELECT). Use this pattern to find the right one:

```python
all_calls = _execute_calls(etl_with_cursor.cursor)
# Print all SQL statements and their params for debugging:
for i, (sql, params) in enumerate(all_calls):
    print(f"Call {i}: {sql[:60]}...")
    print(f"  params: {params}")
```

---

## Understanding the Mock Chain

> ⚠️ This is the most important thing to understand when writing routing tests.

The ETL uses **chained calls**:

```python
# This is how the ETL queries:
result = self.cursor.execute("SELECT ...", params).fetchone()
```

In `MagicMock`, `cursor_mock.execute(...).fetchone()` is **not the same** as
`cursor_mock.fetchone()`. The chained form calls `fetchone` on the
**return value of `execute()`**, which is a separate Mock object:

```python
# ❌ WRONG — configures the wrong mock:
cursor_mock.fetchone.return_value = None

# ✅ CORRECT — configures the chained call:
cursor_mock.execute.return_value.fetchone.return_value = None
```

This distinction matters most for:
- The orphan parent check: `cursor.execute("SELECT 1 FROM DrivingInsightsTrip...").fetchone()`
- The `@@IDENTITY` lookup: `cursor.execute("SELECT @@IDENTITY").fetchone()[0]`
- The `trip_id` lookup: `cursor.execute("SELECT trip_id FROM Trip...").fetchone()`

---

## Bugs Found by These Tests

The test suite discovered **one real production bug** in `sentiance_etl.py`:

### `AttributeError` on `venue: null` in event payloads

**Location:** `process_user_context()` and `process_timeline_events()`  
**Root cause:** `e.get("venue", {})` returns `None` (not `{}`) when the JSON
payload contains `"venue": null`. The default value `{}` is only used when the
**key is absent**, not when the key is present with a `null` value.

```python
# ❌ Before (crashes when venue: null in JSON):
e.get("venue", {}).get("significance")

# ✅ After (handles both absent key and null value):
(e.get("venue") or {}).get("significance")
```

This crash would occur silently in production (caught by the error handler,
logged to `SentianceEventos_Errors`) for any stationary event or timeline event
where the SDK sends an explicit `null` for the venue field.

---

## Future: Regression Tests

The current suite covers **stateless transformation logic only** (Phases 1 & 2).

The planned Phase 3–5 regression tests will use:
- A local **Docker SQL Server** (`development/docker-compose.yml`)
- The `development/hydrate_local_db.py` script to load fixture data
- **Golden-file snapshots** comparing DB state against frozen JSON files

See `etl_testing_strategy.md` in the AI artifacts for the full regression test
design.

To run regression tests (once implemented):

```bash
# Requires Docker running and local DB initialized
.venv/bin/python3 -m pytest tests/regression/ -v -m regression
```
