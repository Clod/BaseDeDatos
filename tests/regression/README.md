# Golden-Snapshot Regression Suite

> **TL;DR** — A frozen corpus of 166 real production events is run through the
> real ETL against the local Docker DB; the resulting state of all 24 tables is
> compared byte-for-byte against blessed golden files. Empty diff = pass.
> Non-empty diff = a regression or an intentional change you must review and
> re-bless. Nobody ever re-checks results by hand again; humans (and LLMs)
> only ever look at *changes*.

```bash
# The one command (requires Docker DB up; DROPS the local VictaTMTK):
.venv/bin/python3 -m pytest tests/regression --run-regression
```

---

## Table of Contents

1. [Philosophy](#1-philosophy)
2. [How it works](#2-how-it-works)
3. [Quick start](#3-quick-start)
4. [The corpus](#4-the-corpus)
5. [Procedures](#5-procedures)
6. [The invariant suite](#6-the-invariant-suite)
7. [The determinism contract](#7-the-determinism-contract)
8. [Findings log](#8-findings-log)
9. [Limits and FAQ](#9-limits-and-faq)

---

## 1. Philosophy

The ETL is **deterministic**: for a fixed set of input events there is exactly
one correct database state. That single fact dictates the whole design.

**Principle 1 — Diff beats judgment.** Because the correct output is exactly
specifiable, the right verification tool is a byte comparison, not an opinion.
A diff catches a swapped lat/lon, a column off by one, a timestamp truncated
at 22 instead of 23 characters — every time, in milliseconds, for free. No
human re-reading and no LLM judge does that reliably. LLMs are reserved for
the two places where judgment is genuinely needed (see Principle 4).

**Principle 2 — 100% real data, selected by structure.** Every corpus case is
an unmodified production event. Cases are *not* hand-picked: a payload's
**structural shape** (the set of its JSON key paths, including which fields
arrived as explicit `null`) is fingerprinted, and the corpus keeps exactly one
representative per shape per event type. Two payloads with the same shape
exercise identical code paths (every `.get()` resolves the same way), so this
gives full structural coverage with ~1% of the volume: 18,556 sampled events
collapse to ~150 shapes.

**Principle 3 — No synthetic data; gaps close themselves.** Four routed event
types have never occurred in production (see §4). We do **not** fabricate
payloads for them — a fabricated payload tests our guess, not the SDK. The
gap is documented in `corpus/manifest.json`, and as real users feed the
database, the top-up procedure (§5.4) harvests real representatives. Coverage
honesty over coverage theater.

**Principle 4 — The blessing is the only judgment call.** Declaring "this
output is correct" happens once per behavior change, in a reviewed git diff of
`golden/`. The *initial* blessing is the only large one, and that is where an
LLM audit (§5.5) earns its keep: cross-checking input payloads against golden
rows against the mapping spec, so a human only adjudicates discrepancies. After
blessing, the LLM is never in the loop again — the suite is pure diff.

**Principle 5 — Two layers, different jobs.** The golden snapshot pins exact
behavior *for the corpus*. The invariant suite (§6) asserts structural truths
that must hold for *any* data — it already caught a production-bound schema
bug on its first run (§8). Invariants also run read-only against production.

---

## 2. How it works

```
corpus/cases/*.json ──┐  (166 frozen real events, loaded with their ids)
                      ▼
        ┌──────────────────────────────┐
        │ 1. DROP + recreate VictaTMTK │   development/sql/init_db.sql
        │ 2. INSERT corpus into        │   identity seeds reset ⇒
        │    SentianceEventos          │   deterministic downstream ids
        │ 3. etl.run() until drained   │   real SentianceETL, bridge OFF
        │ 4. dump all 24 tables        │   snapshot_lib.py normalization
        │ 5. etl.run() once more       │   must be a strict no-op
        └──────────────────────────────┘
                      ▼
   current dump  ⟷  golden/*.jsonl   (committed, reviewed, blessed)
        plus: invariant queries, orphan-ordering scenario
```

| File | Role |
|---|---|
| `corpus/cases/*.json` | Frozen input events (one file per case, committed) |
| `corpus/manifest.json` | Coverage summary + documented gaps + source order |
| `corpus/sources/*.json` | Raw production pulls feeding the builder (committed) |
| `corpus_builder.py` | Shape-fingerprint selection + parent pairing |
| `fetch_topup.py` | Read-only production fetcher for corpus top-ups |
| `snapshot_lib.py` | Canonical dump: normalization rules + table list + diff |
| `harness.py` | DB lifecycle (localhost-only guard, schema reset, loader) |
| `conftest.py` | The session pipeline fixture; dumps frozen before tests run |
| `test_snapshot.py` | Golden comparison + terminal-state check; `--bless` |
| `test_idempotency.py` | Second pass over drained queue must change nothing |
| `test_orphan_ordering.py` | Child-before-parent must park, then complete |
| `test_invariants.py` | Structural truths + snapshot-coverage drift check |
| `golden/*.jsonl` | One canonical JSONL per table — the blessed state |
| `prompts/blessing_audit.md` | LLM prompt for auditing a blessing |
| `audits/` | Output reports of LLM blessing audits |

---

## 3. Quick start

```bash
# 0. Prerequisites: local Docker DB running
cd development && docker-compose up -d && cd ..

# 1. Run the suite (DROPS and rebuilds the local VictaTMTK!)
.venv/bin/python3 -m pytest tests/regression --run-regression

# 2. Plain `pytest` stays safe: without --run-regression everything is skipped,
#    so unit tests and CI keep working untouched.
.venv/bin/python3 -m pytest            # unit suite + skipped regression
```

Runtime: ~11 seconds for the full cycle (schema reset, 166 events, 24-table
dump, double run, 25 invariants).

> ⚠️ The suite **destroys local dev data** in VictaTMTK. If you keep state in
> the local DB, re-hydrate afterwards (`development/hydrate_local_db.py` /
> `hydrate_local_small.py`).

---

## 4. The corpus

**Provenance.** Two committed sources, consumed in this order (order matters —
see id-collision note in `corpus_builder.load_sources`):

1. `development/sample_payloads.json` — 18,556 events (prod rows from the
   Oct 2025 – Feb 2026 window, ids renumbered 1–18556 by the export).
   *Not committed* (gitignored, 60 MB) — but the selected cases are.
2. `corpus/sources/prod_topup_2026-06-11.json` — 21 targeted production rows
   (true prod ids): the DrivingInsights child events with their shared
   parents, TimelineUpdate shape representatives, and the negative cases.

**Selection.** `corpus_builder.py` keeps the lowest-id representative of every
`(tipo, shape)` pair, then force-includes the parent `DrivingInsights` for
every selected child event (a child without its parent would sit parked as an
orphan and its handler would never execute).

**Current coverage (166 cases, 164 shapes):**

| Tipo | Cases | Notes |
|---|---|---|
| requestUserContext | 69 | every structural shape in sample |
| UserContextUpdate | 34 | |
| DrivingInsights | 34 | 32 shapes + 2 forced parents |
| SDKStatus | 7 | |
| TimelineEvents | 6 | legacy type (35 rows ever in prod) |
| TimelineUpdate | 6 | STATIONARY / OFF_THE_GRID / IN_TRANSPORT shapes |
| VehicleCrash | 2 | incl. the `location: null` shape (real crash-path bug) |
| DrivingInsightsPhoneEvents | 2 | |
| DrivingInsightsHarshEvents | 1 | |
| DrivingInsightsSpeedingEvents | 1 | |
| DrivingInsightsCallEvents | 1 | only 2 such events exist in all of prod |
| DebugLog / CRASH / fcm_token | 3 | **negative cases** — must stay untouched |

**Documented gaps** (`manifest.json → routed_tipos_without_coverage`):
`DrivingInsightsWrongWayDrivingEvents`, `TechnicalEvent`, `UserActivity`,
`UserMetadata` — zero occurrences in production as of 2026-06-11. Policy: wait
for real traffic, then §5.4. **Do not write synthetic payloads for them.**

**Negative cases** are real unrouted events (including a `CRASH` row whose
payload is the literal string `Array` — an upstream serialization bug worth
keeping). The golden files prove the ETL leaves them at `is_processed = 0`
with no audit row, and an invariant enforces it for any data.

---

## 5. Procedures

### 5.1 Running the suite

```bash
.venv/bin/python3 -m pytest tests/regression --run-regression
```

Add `-q` for terse output, `-k snapshot` to run only the golden comparison.

### 5.2 Interpreting a failure

A snapshot failure prints a unified diff per table, e.g.:

```
--- golden/Trip.jsonl
+++ current/Trip
-{"trip_id": 12, ..., "distance_meters": "2841.00", ...}
+{"trip_id": 12, ..., "distance_meters": null, ...}
```

Ask, in order:

1. **Did I intend to change this?** If no → it is a regression. The diff tells
   you the table, the row, and the field; fix the code and re-run.
2. **If yes** → is the new value *correct* per `Documentos/MapeoSDK_BD.md`?
   Verify the affected rows (the LLM audit prompt §5.5 can help for large
   diffs), then re-bless (§5.3).
3. **Id-shift noise?** If you edited the corpus, identity values shift and the
   diff is large but mechanical — expected; re-bless after reviewing a sample.

An **idempotency failure** means a second pass mutated data: look for a MERGE
that updates non-idempotently or a row reprocessed despite its flag.
An **invariant failure** is independent of the corpus — read the offending
rows in the assertion message; these are almost always real bugs.

### 5.3 Re-blessing (accepting new behavior)

```bash
.venv/bin/python3 -m pytest tests/regression --run-regression --bless
git diff tests/regression/golden/        # REVIEW THIS — it IS the change
git add tests/regression/golden && git commit
```

The git diff of `golden/` is the reviewable artifact of the behavior change —
treat it with the same seriousness as the code diff that caused it. Never
bless with a dirty working tree mixing unrelated changes.

### 5.4 Topping up the corpus (when production gains new traffic)

Run this when: a gap tipo starts appearing in production, a new event type is
added to the ETL, or the SDK starts sending new payload shapes.

```bash
# 1. Survey what production has now (read-only; via MCP in a Claude session
#    or any SQL client):
#    SELECT tipo, COUNT(*) FROM SentianceEventos GROUP BY tipo

# 2. Harvest real representatives (read-only, needs .env.rds):
.venv/bin/python3 tests/regression/fetch_topup.py \
    --sample-tipo UserMetadata --candidates 12 --max-len 20000
#    ...or explicit rows (children need their parent — survey first):
.venv/bin/python3 tests/regression/fetch_topup.py --ids 81234 81235

# 3. If the new rows are NEWER than snapshot_lib.CORPUS_EPOCH, bump the epoch
#    constant first (fetch_topup refuses otherwise — see §7).

# 4. Rebuild the corpus (source order matters, keep it as in manifest.json):
.venv/bin/python3 tests/regression/corpus_builder.py \
    --sources development/sample_payloads.json \
              tests/regression/corpus/sources/*.json

# 5. Re-bless (§5.3) and audit the NEW cases only (§5.5).
```

### 5.5 LLM blessing audit

The golden files assert *stability*, not *correctness* — the initial blessing
(or new corpus cases) must be audited once against the mapping spec. Open a
Claude Code session in this repo and run the prompt:

```
Follow the instructions in tests/regression/prompts/blessing_audit.md.
Audit scope: <all cases | tipo=X | case ids ...>
```

The audit writes `tests/regression/audits/audit_<date>.md` with a per-case
verdict table (PASS / FAIL / QUESTION). A human resolves every FAIL/QUESTION:
either the ETL is wrong (fix code, re-bless) or the golden is right (record
the resolution in the audit file). A blessing is *trusted* once its audit has
no open items.

### 5.6 Adding a new event type to the ETL — checklist

- [ ] Route added in `run()` + handler implemented (+ unit tests)
- [ ] Real production examples harvested via `fetch_topup.py` (§5.4)
- [ ] Snapshot covers any new table (`snapshot_lib.TABLES` — the coverage
      invariant fails loudly if you forget)
- [ ] Re-bless + audit the new cases

---

## 6. The invariant suite

`test_invariants.py` asserts ~25 structural truths that hold for **any**
ingested data, not just the corpus: every child event row has its parent, every
domain row traces back to an `SdkSourceEvent`, every audit row points at a real
queue row, no provisional trips are stored, no duplicate `(user, transport)`
trips, unrouted tipos never produce audit rows, and the snapshot table list
matches `sys.tables` exactly (a new ETL target table cannot silently escape
snapshotting).

All invariant queries are pure SELECTs. They can be pointed read-only at
**production** as a data-quality smoke check (e.g. from a Claude session via
the `mssql` MCP server, or any SQL client) — that is their second job, and how
the `is_processed BIT` bug (§8) generalizes beyond the corpus.

A failing invariant marked `xfail` is a **tracked known bug**: `strict=True`
means the suite errors the moment the bug is fixed, forcing marker cleanup.

---

## 7. The determinism contract

Why the same corpus always produces byte-identical dumps:

1. **Processing order** — the ETL fetch query is `ORDER BY id` (fixed
   2026-06-11; the docstring always claimed it), the queue is loaded in id
   order, and the pipeline is single-threaded ⇒ identity values across all 24
   tables are reproducible.
2. **Identity reset** — the schema is dropped and recreated each run, so
   identity seeds always start at 1.
3. **Run-time timestamp masking** — every `DATETIME` at-or-after
   `snapshot_lib.CORPUS_EPOCH` (2026-06-10) is masked to `<run-time>`. All
   corpus events predate the epoch, so any timestamp after it can only be
   `GETDATE()` / `datetime.now()` noise. The epoch is **absolute, not
   relative** — masking never changes as wall-clock time passes. Topping up
   with newer events ⇒ bump the epoch ⇒ re-bless (mechanical diff).
4. **GZIP decompressed** — `VARBINARY` columns are stored gzip (whose header
   embeds a timestamp ⇒ raw bytes are not comparable); dumps embed the
   decompressed JSON, which is also what you want to read in a diff.
5. **Stable scalars** — decimals rendered via `str()` (scale fixed by column),
   datetimes truncated to milliseconds, tracebacks reduced to their last line
   (paths and line numbers would churn with unrelated edits).
6. **Bulk echoes excluded** — `SentianceEventos.json` / `Errors.raw_json`
   duplicate corpus inputs and are omitted from dumps.

**Accepted limitation:** inserting a corpus case with an id *between* existing
ones shifts downstream identity values ⇒ a large mechanical re-bless diff.
This is deliberate — the alternative (id virtualization) buys diff-stability
at the cost of dump readability and harness complexity. Corpus edits are rare
and always end in a re-bless anyway.

---

## 8. Findings log

Real issues surfaced by this suite. Keep appending — this section is the
suite's track record.

### 2026-06-11 — `is_processed` BIT collapses the failure marker (first run)

The audit-trail invariant failed on corpus case 707: `is_processed = 1` with
no `SdkSourceEvent`. Root cause: the ETL treats `is_processed` as tri-state
(`0` pending / `1` done / `-1` failed-or-skip), but the column is `BIT` in
`development/sql/init_db.sql` **and in `development/sql/migrate_prod_stage2.sql`
(line ~96) — so the bug would ship to production at go-live.** SQL Server
stores any nonzero value in a BIT as 1 ⇒ every failed row and every
transportId-less orphan is recorded as *successfully processed*. Forensics
then depend entirely on `SentianceEventos_Errors`, and reprocessing-by-flag is
impossible. **Status: FIXED (2026-06-17)** — `SMALLINT` in both SQL files, `xfail` marker
removed from `test_invariants.py`, data dictionary updated. Re-bless required
after recreating the local DB.

### 2026-06-11 — `process_crash_event` crashes on `location: null`

Corpus case 707 (real VehicleCrash payload with `"location": null`) raised
`AttributeError` at `sentiance_etl.py:820` — `payload.get("location", {})`
returned `None` when the key is present-but-null. **Status: FIXED (2026-06-17)**
— changed to `payload.get("location") or {}`, same idiom already used in
`process_user_context` / `process_timeline_events`. Unit test added in
`test_param_extraction.py::TestProcessCrashEventParams::test_null_location_does_not_crash`.
Golden snapshot re-blessed: case 707 now produces a `VehicleCrashEvent` row.

### 2026-06-11 — production sends `UserActivityUpdate`, ETL routes `UserActivity`

112 production rows (Oct 2025) carry `tipo = 'UserActivityUpdate'`, which no
routing entry matches — they will sit at `is_processed = 0` forever once
Stage 2 goes live. Possibly a deprecated SDK name. **Status: OPEN decision** —
either add it to the routing filter (then harvest corpus cases for it) or
explicitly document it as ignored (then add it to the negative tipos).

---

## 9. Limits and FAQ

**The golden encodes current behavior — including current bugs.** That is by
design: the suite pins *what is*, the audit (§5.5) and findings log establish
*what should be*. Fixing a known bug produces a clean, reviewable golden diff.

**What this suite does NOT cover:** the four gap tipos (no production traffic
yet), the Movilidad bridge (forced off in the harness; it has its own unit
tests), DB connection failure/retry behavior (`reconnect()` paths), and true
concurrency (the pipeline is single-threaded by design).

**Why are corpus payloads committed — isn't that user data?** Same precedent
as `development/test_small_full.json` (already committed): this is a private
repo and the corpus is the test's foundation. If policy changes, the corpus
can be regenerated from sources kept outside git.

**Why not pytest-syrupy / snapshot libraries?** The snapshot is a SQL Server
dump, not a Python value; the custom dumper is ~150 lines and owns the
normalization rules, which are the actual hard part.

**Can I run only the invariants against production?** Yes — they are pure
SELECTs; run them via the read-only `mssql` MCP server or any SQL client.
Do not point the *snapshot* harness at production: it refuses by construction
(`harness.assert_local_only`), and keep it that way.
