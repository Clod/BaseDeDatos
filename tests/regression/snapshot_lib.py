"""
snapshot_lib.py — Deterministic database-state snapshots for the regression suite.

Dumps every ETL target table to a canonical JSONL representation that is
byte-for-byte reproducible across runs, so that the golden files in
tests/regression/golden/ can be compared with a plain text diff.

Normalization rules (the "determinism contract", see README.md §7):

1.  Rows are ordered by their identity primary key (insertion order, which is
    deterministic because the ETL processes SentianceEventos ORDER BY id).
2.  Columns appear in schema order; excluded columns (bulky payload echoes)
    are listed per table in EXCLUDED_COLUMNS.
3.  DATETIME values >= CORPUS_EPOCH are masked to "<run-time>": every corpus
    event predates the epoch, so any timestamp at-or-after it can only have
    been generated *during* the run (GETDATE() defaults, datetime.now()
    fallbacks) and would otherwise change on every execution.
4.  VARBINARY columns hold GZIP-compressed JSON; they are decompressed and
    embedded as parsed objects so diffs are readable. (The raw bytes are NOT
    comparable across runs: the gzip header embeds a timestamp.)
5.  Decimal values are rendered as str(value) — scale is fixed by the column
    definition, so this is stable.
6.  Error tracebacks keep only their final line (exception type + message);
    absolute paths and line numbers would churn with unrelated edits.
"""

from __future__ import annotations

import difflib
import gzip
import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

# Any timestamp at-or-after this moment is considered "generated at run time"
# and is masked. Bump this (and re-bless) whenever the corpus is topped up
# with newer production events. Corpus events MUST predate this epoch.
CORPUS_EPOCH = datetime(2026, 6, 10, 0, 0, 0)

MASK = "<run-time>"

GOLDEN_DIR = Path(__file__).parent / "golden"

# Every table the ETL writes to. test_invariants.py cross-checks this list
# against sys.tables so a new target table cannot silently escape snapshotting.
TABLES: tuple[str, ...] = (
    "SentianceEventos",
    "SentianceEventos_Errors",
    "SdkSourceEvent",
    "UserMetadata",
    "Trip",
    "DrivingInsightsTrip",
    "DrivingInsightsHarshEvent",
    "DrivingInsightsPhoneEvent",
    "DrivingInsightsCallEvent",
    "DrivingInsightsSpeedingEvent",
    "DrivingInsightsWrongWayDrivingEvent",
    "UserContextHeader",
    "UserContextUpdateCriteria",
    "UserHomeHistory",
    "UserWorkHistory",
    "UserContextActiveSegmentDetail",
    "UserContextSegmentAttribute",
    "UserContextEventDetail",
    "TimelineEventHistory",
    "UserActivityHistory",
    "TechnicalEventHistory",
    "VehicleCrashEvent",
    "SdkStatusHistory",
    "UserOrganization",
)

# Tables that exist in the schema but are NOT ETL output (infrastructure /
# input). They are still snapshotted (SentianceEventos final state proves the
# routing decisions) unless listed in EXCLUDED_COLUMNS with their bulk fields.
EXCLUDED_COLUMNS: dict[str, set[str]] = {
    # 'json' is the raw input payload — it already lives in corpus/cases/.
    "SentianceEventos": {"json"},
    # 'raw_json' duplicates the input payload as well.
    "SentianceEventos_Errors": {"raw_json"},
}

# Columns whose value is a Python traceback; normalized to the last line.
TRACEBACK_COLUMNS: set[str] = {"error_message"}


def _normalize_value(value: Any, column: str) -> Any:
    """Maps a raw pyodbc value to its canonical JSON representation."""
    if value is None:
        return None
    if isinstance(value, datetime):
        if value >= CORPUS_EPOCH:
            return MASK
        return value.strftime("%Y-%m-%d %H:%M:%S.") + f"{value.microsecond // 1000:03d}"
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (bytes, bytearray)):
        try:
            return json.loads(gzip.decompress(bytes(value)).decode("utf-8"))
        except Exception:
            return f"<binary:{len(value)} bytes (not gzip-json)>"
    if isinstance(value, str) and column in TRACEBACK_COLUMNS:
        lines = [ln for ln in value.strip().splitlines() if ln.strip()]
        return lines[-1] if lines else value
    if isinstance(value, bool):
        return value
    return value


def dump_table(cursor: Any, table: str) -> list[str]:
    """Returns the canonical JSONL lines for one table (may be empty)."""
    excluded = EXCLUDED_COLUMNS.get(table, set())
    cursor.execute(f"SELECT * FROM {table} ORDER BY 1")
    columns = [d[0] for d in cursor.description]
    lines: list[str] = []
    for row in cursor.fetchall():
        record = {
            col: _normalize_value(val, col)
            for col, val in zip(columns, row)
            if col not in excluded
        }
        lines.append(json.dumps(record, ensure_ascii=False, default=str))
    return lines


def dump_db_state(cursor: Any) -> dict[str, list[str]]:
    """Dumps every table in TABLES. Returns {table_name: [jsonl lines]}."""
    return {table: dump_table(cursor, table) for table in TABLES}


def write_golden(state: dict[str, list[str]], golden_dir: Path = GOLDEN_DIR) -> None:
    """Writes (blesses) a dump as the new golden files."""
    golden_dir.mkdir(parents=True, exist_ok=True)
    for table, lines in state.items():
        path = golden_dir / f"{table}.jsonl"
        path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def load_golden(golden_dir: Path = GOLDEN_DIR) -> dict[str, list[str]]:
    """Loads the committed golden files. Missing files -> empty table."""
    state: dict[str, list[str]] = {}
    for table in TABLES:
        path = golden_dir / f"{table}.jsonl"
        if path.exists():
            text = path.read_text(encoding="utf-8")
            state[table] = text.splitlines() if text else []
        else:
            state[table] = []
    return state


def diff_states(
    golden: dict[str, list[str]],
    current: dict[str, list[str]],
    context_lines: int = 2,
    max_lines_per_table: int = 60,
) -> str:
    """Returns a human-readable unified diff between two dumps ('' if equal)."""
    chunks: list[str] = []
    for table in TABLES:
        old, new = golden.get(table, []), current.get(table, [])
        if old == new:
            continue
        diff = list(
            difflib.unified_diff(
                old,
                new,
                fromfile=f"golden/{table}.jsonl",
                tofile=f"current/{table}",
                n=context_lines,
                lineterm="",
            )
        )
        if len(diff) > max_lines_per_table:
            omitted = len(diff) - max_lines_per_table
            diff = diff[:max_lines_per_table] + [f"... ({omitted} more diff lines)"]
        chunks.append("\n".join(diff))
    return "\n\n".join(chunks)
