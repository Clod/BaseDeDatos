# Blessing Audit — LLM Verification of the Golden Snapshot

You are auditing the golden snapshot of the Sentiance ETL regression suite.
The golden files assert that the pipeline's output is *stable*; your job is to
establish, once, that it is *correct*. You verify that every audited corpus
case was transformed into exactly the database rows the mapping specification
requires — field by field, transform by transform.

You are an auditor, not a fixer: **you must not modify any code, corpus,
or golden file.** Your only output is the audit report.

## Inputs (read these first)

| Artifact | Path |
|---|---|
| Mapping specification (authoritative) | `Documentos/MapeoSDK_BD.md` |
| Data dictionary | `Documentos/DiccionarioDatos.md` |
| ETL implementation (ground truth of *what ran*) | `etl/sentiance_etl.py` |
| Corpus cases (inputs) | `tests/regression/corpus/cases/*.json` |
| Corpus manifest (coverage + roles) | `tests/regression/corpus/manifest.json` |
| Golden output (one JSONL per table) | `tests/regression/golden/*.jsonl` |
| Normalization rules (how values were canonicalized) | `tests/regression/snapshot_lib.py` |
| Known open findings (do not re-report) | `tests/regression/README.md` §8 |

## Audit scope

The invoker specifies the scope (all cases, one tipo, or explicit case ids).
If unspecified, audit every case whose tipo has fewer than 10 cases, plus 5
randomly chosen cases from each high-volume tipo (requestUserContext,
UserContextUpdate, DrivingInsights).

## How to trace a case through the golden files

1. Read the case file: `id` is the `SentianceEventos` row id; `json` is the
   raw input payload; `meta.role` is `representative`, `forced-parent`,
   `negative`, or `expected_orphan: true`.
2. In `golden/SentianceEventos.jsonl`, find the row with that `id` — check its
   final `is_processed` state matches the case's role (see rules below).
3. In `golden/SdkSourceEvent.jsonl`, find rows with
   `sentiance_eventos_id == id`; note their `sdk_source_event_id` (call it
   SID).
4. Follow SID into the domain tables for the case's tipo
   (e.g. `DrivingInsightsTrip` via `sdk_source_event_id`, then its children
   via `driving_insights_trip_id`; `UserContextHeader` then its children via
   `user_context_payload_id`; `Trip` via `creating_/last_updated_by_
   sdk_source_event_id` or `canonical_transport_event_id`).
5. Compare every column value against the input payload per the mapping spec.

## What to verify per case (the rubric)

- **Routing**: the tipo produced rows in exactly the tables the spec maps it
  to — no missing tables, no unexpected extras.
- **Field mapping**: each column equals the spec'd source field. Watch
  especially for: latitude/longitude swaps, start/end time swaps,
  epoch-vs-ISO confusion, score fields mapped to the wrong score column.
- **Transforms**:
  - Timestamps: ISO `T`→space, no `Z`, truncated to milliseconds (23 chars).
  - `<run-time>` masks are LEGITIMATE for `created_at`-style columns and for
    `source_time` when the payload has no `startTime` (fallback is
    `datetime.now()`); a `<run-time>` where the payload HAS a real timestamp
    is a FAIL.
  - GZIP columns appear decompressed in the dump: their content must equal
    the payload's corresponding array/object exactly.
  - `payload_hash` = SHA-256 hex of the raw `json` string (spot-check one per
    tipo by computing it).
  - Null handling: payload `null` → SQL `NULL`, never `0` / `""` / crash.
- **Trip consolidation**: `isProvisional: true` transport events must NOT
  create `Trip` rows; final events must upsert exactly one row per
  `(user, transport id)`.
- **Negative cases** (`role: negative`): the row stays `is_processed = 0` (or
  `false`), with NO SdkSourceEvent and NO domain rows.
- **Expected orphans** (`expected_orphan: true`): same parked state — the
  parent is genuinely absent from production.
- **Errors**: a case appearing in `SentianceEventos_Errors` is a FAIL unless
  it is already listed in README §8 (known open findings) — then note it as
  KNOWN instead.

## Report format

Write the report to `tests/regression/audits/audit_<YYYY-MM-DD>.md`:

```markdown
# Blessing Audit — <date>
Scope: <scope>   Golden as of: <git short hash>   Auditor: <model name>

| Case | Tipo | Verdict | Notes |
|---|---|---|---|
| 707 | VehicleCrash | KNOWN | location:null crash — README §8 |
| 1042 | DrivingInsights | PASS | all scores, trip upsert, gzip waypoints OK |
| ...  | ... | FAIL | end_time holds payload startTime (col swap?) |

## FAIL details
<one subsection per FAIL: input fragment, golden fragment, spec citation>

## QUESTION details
<anything ambiguous in the spec itself — cite the ambiguity>

## Summary
<n PASS / n FAIL / n QUESTION / n KNOWN; overall recommendation:
 TRUST / FIX-THEN-REBLESS>
```

Verdicts: **PASS** (all rubric points hold), **FAIL** (a concrete mismatch,
with evidence), **QUESTION** (spec ambiguous or silent — a human must decide),
**KNOWN** (matches an open finding in README §8).

## Rules

- Evidence or it didn't happen: every FAIL must quote the input fragment, the
  golden fragment, and the spec line it violates.
- Verify against the SPEC first, the code second. If golden matches the code
  but contradicts the spec, that is a FAIL (the code is wrong), not a PASS.
- If the spec and the data dictionary disagree, raise a QUESTION.
- Do not re-derive the whole golden — audit the scoped cases only.
- Do not modify anything outside `tests/regression/audits/`.
