"""
corpus_builder.py — Selects the frozen regression corpus from real event dumps.

Reads one or more source dumps of SentianceEventos rows (the format produced
by development/fetch_sample_data.py: original_id / sentianceid / json / tipo /
created_at / app_version) and selects a minimal corpus that covers every
*structural shape* the SDK has actually sent, per event type.

Selection method — shape fingerprinting:
    A payload's "shape" is the set of its JSON key paths, where each leaf
    also records whether its value was explicitly null. Two payloads with
    identical shapes exercise exactly the same code paths in the ETL handlers
    (every .get() resolves the same way), so one representative per shape is
    sufficient. The representative chosen is the record with the LOWEST id,
    which makes re-running the builder deterministic.

Parent pairing:
    DrivingInsights*Events child types require their parent DrivingInsights
    record (same transportId + user) to be present, otherwise the ETL parks
    them as orphans forever. For every selected child, the builder force-
    includes the matching parent if it exists anywhere in the sources;
    otherwise the case is tagged "expected_orphan": true and the golden files
    will show it remaining at is_processed = 0 — which is itself correct,
    documented behavior.

Usage:
    python tests/regression/corpus_builder.py \
        --sources development/sample_payloads.json tests/regression/corpus/sources/*.json \
        --out tests/regression/corpus

NEVER edit case files by hand — the corpus must remain 100% real production
traffic. See README.md §4 for the no-synthetic-data policy.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("corpus_builder")

# Event types the ETL routes (etl/sentiance_etl.py run()).
ROUTED_TIPOS: tuple[str, ...] = (
    "DrivingInsights",
    "DrivingInsightsHarshEvents",
    "DrivingInsightsPhoneEvents",
    "DrivingInsightsCallEvents",
    "DrivingInsightsSpeedingEvents",
    "DrivingInsightsWrongWayDrivingEvents",
    "UserContextUpdate",
    "requestUserContext",
    "TimelineEvents",
    "VehicleCrash",
    "SDKStatus",
    "UserMetadata",
    "TechnicalEvent",
    "UserActivity",
    "TimelineUpdate",
)

CHILD_TIPOS: tuple[str, ...] = (
    "DrivingInsightsHarshEvents",
    "DrivingInsightsPhoneEvents",
    "DrivingInsightsCallEvents",
    "DrivingInsightsSpeedingEvents",
    "DrivingInsightsWrongWayDrivingEvents",
)

# Unrouted types deliberately included as negative cases: the golden files
# must show them untouched (is_processed = 0, no SdkSourceEvent row).
NEGATIVE_TIPOS: tuple[str, ...] = ("DebugLog", "CRASH", "fcm_token")

# Tipo comparison must be case-insensitive, mirroring SQL Server's default
# collation (production contains e.g. 'userContextUpdate').
_ROUTED_FOLDED = {t.lower(): t for t in ROUTED_TIPOS}
_NEGATIVE_FOLDED = {t.lower(): t for t in NEGATIVE_TIPOS}


def shape_paths(obj: Any, prefix: str = "") -> set[str]:
    """Returns the structural fingerprint paths of a parsed JSON value."""
    paths: set[str] = set()
    if isinstance(obj, dict):
        for key, value in obj.items():
            path = f"{prefix}.{key}"
            if value is None:
                paths.add(path + ":null")
            elif isinstance(value, (dict, list)):
                paths.add(path)
                paths |= shape_paths(value, path)
            else:
                paths.add(path)
    elif isinstance(obj, list):
        for item in obj[:20]:
            paths |= shape_paths(item, prefix + "[]")
    return paths


def shape_fingerprint(payload: Any) -> str:
    """Stable 10-hex-char digest of a payload's structural shape."""
    canonical = "\n".join(sorted(shape_paths(payload)))
    return hashlib.sha1(canonical.encode("utf-8")).hexdigest()[:10]


def _record_id(record: dict[str, Any]) -> int:
    rid = record.get("_corpus_id")
    if rid is None:
        rid = record.get("original_id") or record["id"]
    return int(rid)


def load_sources(paths: list[Path]) -> list[dict[str, Any]]:
    """Loads and concatenates source dumps, de-duplicating by record id.

    Id collisions across files are real: development/sample_payloads.json uses
    renumbered ids (1..N), while top-up dumps carry true production ids. When
    two different payloads claim the same id, the later one (in CLI order) is
    deterministically shifted by +50,000,000 — so keep the source order stable
    when rebuilding (it is recorded in corpus/manifest.json).
    """
    seen: dict[int, dict[str, Any]] = {}
    for path in paths:
        records = json.loads(path.read_text(encoding="utf-8"))
        for record in records:
            record["_source"] = path.name
            rid = _record_id(record)
            while rid in seen and seen[rid]["json"] != record["json"]:
                rid += 50_000_000
            if rid not in seen:
                record["_corpus_id"] = rid
                seen[rid] = record
        logger.info("Loaded %d records from %s", len(records), path.name)
    return sorted(seen.values(), key=_record_id)


def _parse(record: dict[str, Any]) -> Any | None:
    try:
        return json.loads(record["json"])
    except (json.JSONDecodeError, TypeError, KeyError):
        return None


def select_corpus(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One representative (lowest id) per (tipo, shape), plus forced parents."""
    by_shape: dict[tuple[str, str], dict[str, Any]] = {}
    shape_counts: dict[str, set[str]] = defaultdict(set)

    for record in records:
        folded = (record.get("tipo") or "").lower()
        canonical_tipo = _ROUTED_FOLDED.get(folded) or _NEGATIVE_FOLDED.get(folded)
        if canonical_tipo is None:
            continue
        payload = _parse(record)
        if payload is None:
            if folded not in _NEGATIVE_FOLDED:
                continue
            # Negative cases may carry non-JSON payloads (e.g. the literal
            # string 'Array' from an upstream serialization bug) — the ETL
            # must leave them untouched either way, so keep them.
            fingerprint = "rawnonjson"
        else:
            fingerprint = shape_fingerprint(payload)
        shape_counts[canonical_tipo].add(fingerprint)
        key = (canonical_tipo, fingerprint)
        if key not in by_shape or _record_id(record) < _record_id(by_shape[key]):
            by_shape[key] = record

    selected = {
        _record_id(r): {**r, "_role": "representative", "_shape": fp, "_tipo_canonical": tipo}
        for (tipo, fp), r in by_shape.items()
    }

    # Force-include the parent DrivingInsights for every selected child.
    parents_by_transport: dict[tuple[str, str], dict[str, Any]] = {}
    for record in records:
        if (record.get("tipo") or "").lower() != "drivinginsights":
            continue
        payload = _parse(record)
        if not isinstance(payload, dict):
            continue
        transport_id = (payload.get("transportEvent") or {}).get("id")
        if transport_id:
            key = (transport_id, record.get("sentianceid") or "")
            if key not in parents_by_transport:
                parents_by_transport[key] = record

    for case in list(selected.values()):
        if case["_tipo_canonical"] not in CHILD_TIPOS:
            continue
        payload = _parse(case)
        transport_id = payload.get("transportId") if isinstance(payload, dict) else None
        parent = parents_by_transport.get((transport_id, case.get("sentianceid") or ""))
        if parent is None:
            case["_expected_orphan"] = True
            logger.warning(
                "Child %s id=%s has no parent DrivingInsights in sources -> expected_orphan",
                case["_tipo_canonical"],
                _record_id(case),
            )
        elif _record_id(parent) not in selected:
            selected[_record_id(parent)] = {
                **parent,
                "_role": "forced-parent",
                "_shape": shape_fingerprint(_parse(parent)),
                "_tipo_canonical": "DrivingInsights",
            }

    logger.info(
        "Selected %d cases covering %d shapes across %d tipos",
        len(selected),
        sum(len(s) for s in shape_counts.values()),
        len(shape_counts),
    )
    return sorted(selected.values(), key=_record_id)


def write_corpus(
    cases: list[dict[str, Any]], out_dir: Path, sources: list[str] | None = None
) -> None:
    """Writes one JSON file per case plus the manifest. Replaces cases/ content."""
    cases_dir = out_dir / "cases"
    cases_dir.mkdir(parents=True, exist_ok=True)
    for stale in cases_dir.glob("*.json"):
        stale.unlink()

    tipo_summary: dict[str, dict[str, int]] = defaultdict(lambda: {"cases": 0, "shapes": 0})
    shapes_seen: dict[str, set[str]] = defaultdict(set)

    for case in cases:
        case_id = _record_id(case)
        tipo = case["_tipo_canonical"]
        role = case.get("_role", "representative")
        if tipo in _NEGATIVE_FOLDED.values():
            role = "negative"
        body = {
            "id": case_id,
            "sentianceid": case.get("sentianceid"),
            "tipo": case["tipo"],
            "json": case["json"],
            "meta": {
                "role": role,
                "shape": case["_shape"],
                "source": case["_source"],
                "created_at": case.get("created_at"),
                "app_version": case.get("app_version"),
                **({"expected_orphan": True} if case.get("_expected_orphan") else {}),
                **(
                    {"source_record_id": int(case.get("original_id") or case["id"])}
                    if case_id != int(case.get("original_id") or case["id"])
                    else {}
                ),
            },
        }
        filename = f"{tipo}__{case_id}__{case['_shape']}.json"
        (cases_dir / filename).write_text(
            json.dumps(body, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        tipo_summary[tipo]["cases"] += 1
        shapes_seen[tipo].add(case["_shape"])

    for tipo, shapes in shapes_seen.items():
        tipo_summary[tipo]["shapes"] = len(shapes)

    covered = set(tipo_summary)
    manifest = {
        "built_at": datetime.now().strftime("%Y-%m-%d"),
        "sources_in_order": sources or [],
        "total_cases": len(cases),
        "tipos": dict(sorted(tipo_summary.items())),
        "routed_tipos_without_coverage": sorted(set(ROUTED_TIPOS) - covered),
        "policy": (
            "No synthetic data. Gaps close only by topping up from production "
            "as real traffic accumulates (README.md, 'Topping up the corpus')."
        ),
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    logger.info("Wrote %d cases to %s", len(cases), cases_dir)
    if manifest["routed_tipos_without_coverage"]:
        logger.warning(
            "UNCOVERED routed tipos (no production traffic yet): %s",
            ", ".join(manifest["routed_tipos_without_coverage"]),
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--sources", nargs="+", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path(__file__).parent / "corpus")
    args = parser.parse_args()
    records = load_sources(args.sources)
    cases = select_corpus(records)
    write_corpus(cases, args.out, [p.name for p in args.sources])


if __name__ == "__main__":
    main()
