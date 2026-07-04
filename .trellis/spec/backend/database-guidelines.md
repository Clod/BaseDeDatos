# Database Guidelines

> Database patterns and conventions for this project.

---

## Overview

<!--
Document your project's database conventions here.

Questions to answer:
- What ORM/query library do you use?
- How are migrations managed?
- What are the naming conventions for tables/columns?
- How do you handle transactions?
-->

(To be filled by the team)

---

## Query Patterns

### Idempotency & Reprocessing

The ETL processes each `SentianceEventos` row once, gated by the `is_processed`
tri-state (`0` pending / `1` ok / `-1` error; sentinel `9` = out-of-window).
Writes fall into three idempotency classes — match the class when adding a new
target table in `etl/sentiance_etl.py`:

| Class | Tables | Pattern | Key |
|-------|--------|---------|-----|
| Shared / mutable | `Trip`, `DrivingInsightsTrip` | `MERGE` (update in place, PK stable) | `(canonical_transport_event_id, sentiance_user_id)` |
| Leaf events | `DrivingInsightsHarshEvent`/`Phone`/`Call`/`Speeding`/`WrongWay`, `UserMetadata` | `INSERT ... SELECT ... WHERE NOT EXISTS` | natural key, **exact columns only** |
| Append-only | Timeline, UserContext sub-tree, SdkStatus, UserActivity, TechnicalEvent, VehicleCrash | not guarded — cleaned by the purge tool | via `SdkSourceEvent` audit link |

Reprocessing a window (reset `is_processed=0` + re-run) is only safe after a
clean slate: run `scripts/purge_for_reprocess.py --uid|--ids|--since|--until`
(supports `--dry-run`) which deletes downstream rows via the `SdkSourceEvent`
audit link + UserContext sub-tree, then run `etl/run_full_pipeline.py`.

Tests: `tests/regression/test_reprocess.py` (subtree not duplicated) and
`test_purge_reprocess.py` (purge + reprocess rebuilds identically).

---

## Migrations

<!-- How to create and run migrations -->

(To be filled by the team)

---

## Naming Conventions

<!-- Table names, column names, index names -->

(To be filled by the team)

---

## Common Mistakes

- **Bare `INSERT` on a re-runnable path.** Resetting `is_processed=0` and
  re-running duplicated `DrivingInsightsTrip` and its child events (harsh counts
  doubled downstream in the Movilidad bridge). Fix: `MERGE` for shared rows,
  `NOT EXISTS` for leaf events. See *Query Patterns → Idempotency*.
- **Float columns in a `NOT EXISTS` natural key.** `magnitude numeric(6,3)`
  rounds on write, so `... AND magnitude = ?` failed to match on reprocess and
  duplicated anyway. Use exact columns only (epoch + type), never floats.
- **Reprocessing without purging first.** Append-only tables (Timeline,
  UserContext, ...) duplicate on a plain re-run — always run
  `scripts/purge_for_reprocess.py` before reprocessing a window.
