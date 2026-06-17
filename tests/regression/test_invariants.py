"""
test_invariants.py — Structural truths that must hold for ANY ingested data.

Unlike the golden snapshot (which pins exact output for the frozen corpus),
these assertions express properties of the data model itself, so they catch
problems on data the corpus has never seen. Each query returns OFFENDING rows;
the invariant holds when the result set is empty.

The same queries are safe to run read-only against production as a smoke
check (see README.md §6) — they contain only SELECTs.
"""

from __future__ import annotations

import pytest

from . import snapshot_lib

pytestmark = pytest.mark.regression

_CHILD_TABLES = (
    "DrivingInsightsHarshEvent",
    "DrivingInsightsPhoneEvent",
    "DrivingInsightsCallEvent",
    "DrivingInsightsSpeedingEvent",
    "DrivingInsightsWrongWayDrivingEvent",
)

_UC_CHILD_TABLES = (
    "UserContextUpdateCriteria",
    "UserHomeHistory",
    "UserWorkHistory",
    "UserContextActiveSegmentDetail",
    "UserContextEventDetail",
)

_SOURCE_LINKED_TABLES = (
    "DrivingInsightsTrip",
    "TimelineEventHistory",
    "UserActivityHistory",
    "TechnicalEventHistory",
    "VehicleCrashEvent",
    "SdkStatusHistory",
    "UserContextHeader",
)

INVARIANTS: list[tuple[str, str]] = []

for _t in _CHILD_TABLES:
    INVARIANTS.append((
        f"{_t}: every row has its parent DrivingInsightsTrip",
        f"SELECT TOP 5 c.* FROM {_t} c LEFT JOIN DrivingInsightsTrip p "
        "ON p.driving_insights_trip_id = c.driving_insights_trip_id "
        "WHERE p.driving_insights_trip_id IS NULL",
    ))

for _t in _UC_CHILD_TABLES:
    INVARIANTS.append((
        f"{_t}: every row has its UserContextHeader",
        f"SELECT TOP 5 c.* FROM {_t} c LEFT JOIN UserContextHeader h "
        "ON h.user_context_payload_id = c.user_context_payload_id "
        "WHERE h.user_context_payload_id IS NULL",
    ))

for _t in _SOURCE_LINKED_TABLES:
    INVARIANTS.append((
        f"{_t}: every row traces back to an SdkSourceEvent",
        f"SELECT TOP 5 t.* FROM {_t} t LEFT JOIN SdkSourceEvent s "
        "ON s.sdk_source_event_id = t.sdk_source_event_id "
        "WHERE s.sdk_source_event_id IS NULL",
    ))

INVARIANTS += [
    (
        "SdkSourceEvent: every audit row points at a real SentianceEventos row",
        "SELECT TOP 5 s.* FROM SdkSourceEvent s LEFT JOIN SentianceEventos e "
        "ON e.id = s.sentiance_eventos_id WHERE e.id IS NULL",
    ),
    (
        "SentianceEventos: every processed row has an SdkSourceEvent audit trail",
        "SELECT TOP 5 e.id, e.tipo FROM SentianceEventos e "
        "WHERE e.is_processed = 1 AND NOT EXISTS "
        "(SELECT 1 FROM SdkSourceEvent s WHERE s.sentiance_eventos_id = e.id)",
    ),
    (
        "Trip: provisional trips are never stored",
        "SELECT TOP 5 trip_id, canonical_transport_event_id FROM Trip WHERE is_provisional = 1",
    ),
    (
        "Trip: no duplicate (user, transport event) pairs",
        "SELECT TOP 5 sentiance_user_id, canonical_transport_event_id, COUNT(*) AS n "
        "FROM Trip GROUP BY sentiance_user_id, canonical_transport_event_id HAVING COUNT(*) > 1",
    ),
    (
        "DrivingInsightsTrip: trip_id, when set, references a real Trip",
        "SELECT TOP 5 d.driving_insights_trip_id, d.trip_id FROM DrivingInsightsTrip d "
        "LEFT JOIN Trip t ON t.trip_id = d.trip_id "
        "WHERE d.trip_id IS NOT NULL AND t.trip_id IS NULL",
    ),
    (
        "UserContextSegmentAttribute: every attribute has its segment detail",
        "SELECT TOP 5 a.* FROM UserContextSegmentAttribute a "
        "LEFT JOIN UserContextActiveSegmentDetail d "
        "ON d.user_context_active_segment_detail_id = a.user_context_active_segment_detail_id "
        "WHERE d.user_context_active_segment_detail_id IS NULL",
    ),
    (
        "Unrouted tipos never generate audit rows",
        "SELECT TOP 5 s.* FROM SdkSourceEvent s "
        "WHERE s.record_type IN ('DebugLog', 'CRASH', 'fcm_token')",
    ),
]


_ids = [p.values[0] if hasattr(p, "values") else p[0] for p in INVARIANTS]


@pytest.mark.parametrize("description,sql", INVARIANTS, ids=_ids)
def test_invariant(db_cursor, description: str, sql: str) -> None:
    rows = db_cursor.execute(sql).fetchall()
    assert rows == [], f"Invariant violated — {description}. Offending rows: {rows[:5]}"


def test_snapshot_covers_every_table(db_cursor) -> None:
    """A new ETL target table must be added to snapshot_lib.TABLES on purpose."""
    db_cursor.execute("SELECT name FROM sys.tables")
    in_db = {row[0] for row in db_cursor.fetchall()}
    expected = set(snapshot_lib.TABLES)
    assert in_db == expected, (
        f"Snapshot coverage drift. Tables in DB but not snapshotted: "
        f"{sorted(in_db - expected)}; snapshotted but missing from DB: "
        f"{sorted(expected - in_db)}. Update snapshot_lib.TABLES deliberately."
    )
