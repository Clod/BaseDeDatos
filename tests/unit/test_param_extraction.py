"""
test_param_extraction.py — Phase 2: Unit tests for SQL parameter extraction
in each SentianceETL.process_*() method.

APPROACH:
    Each process_* method builds a tuple of parameters and passes it to
    cursor.execute(sql, params). We capture those calls via the mock_cursor
    fixture (a MagicMock) and assert the correct values were extracted from
    the input JSON payload.

    We are NOT testing SQL Server behavior. We are testing that:
    1. The right fields are read from the JSON (correct key names).
    2. Transformations are applied (format_ts, compress_data, bool coercion).
    3. None is passed when an optional field is absent.
    4. Sub-objects are correctly destructured (e.g. location.latitude).

FIXTURES (from conftest.py):
    etl_with_cursor — SentianceETL instance with conn + cursor as MagicMock.
                      cursor.fetchone() returns (999,) by default (fake @@IDENTITY).

HELPER:
    _get_execute_call(mock_cursor, n) — returns the (sql, params) tuple from
    the nth cursor.execute() call (0-indexed).
"""

import gzip
import json
import pytest
from unittest.mock import call


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _execute_calls(mock_cursor):
    """Return list of (sql, params) from all cursor.execute() calls."""
    return [(c.args[0], c.args[1] if len(c.args) > 1 else None)
            for c in mock_cursor.execute.call_args_list]


def _get_call_params(mock_cursor, index):
    """Return just the params tuple from the nth execute() call."""
    calls = _execute_calls(mock_cursor)
    return calls[index][1]


def _decompress(blob):
    """Decompress a GZIP blob and parse as JSON."""
    return json.loads(gzip.decompress(blob))


# ---------------------------------------------------------------------------
# process_driving_insights
# ---------------------------------------------------------------------------

class TestProcessDrivingInsightsParams:
    """
    process_driving_insights() triggers:
      Call 0: upsert_trip → MERGE Trip (we skip asserting MERGE internals here)
      Call 1: SELECT trip_id FROM Trip  (fetchone returns 999)
      Call 2: INSERT INTO DrivingInsightsTrip
      Call 3: SELECT @@IDENTITY  (fetchone returns 999 → di_id)
      (No harsh/phone/call/speeding events in this fixture)
    """

    @pytest.fixture
    def payload(self):
        return {
            "safetyScores": {
                "smoothScore": 0.858,
                "focusScore": 0.590,
                "legalScore": 0.942,
                "callWhileMovingScore": 1.0,
                "overallScore": 0.797,
                "harshBrakingScore": 0.900,
                "harshTurningScore": 1.0,
                "harshAccelerationScore": 0.950,
                "wrongWayDrivingScore": None,
                "attentionScore": 0.847,
            },
            "transportEvent": {
                "id": "transport-abc",
                "startTime": "2026-04-01T10:00:00.000Z",
                "endTime": "2026-04-01T10:30:00.000Z",
                "lastUpdateTime": "2026-04-01T10:30:00.000Z",
                "lastUpdateTimeEpoch": 1743504600000,
                "startTimeEpoch": 1743502800000,
                "endTimeEpoch": 1743504600000,
                "durationInSeconds": 1800,
                "distance": 5399,
                "transportMode": "CAR",
                "occupantRole": "DRIVER",
                "isProvisional": False,
                "transportTags": {},
                "waypoints": [{"latitude": -34.55, "longitude": -58.48}],
            },
            "harshDrivingEvents": [],
            "phoneUsageEvents": [],
            "callWhileMovingEvents": [],
            "speedingEvents": [],
        }

    def test_all_scores_extracted(self, etl_with_cursor, payload):
        etl_with_cursor.process_driving_insights(sid=1, uid="user-1", payload=payload)
        # DrivingInsightsTrip INSERT is the 3rd execute call (index 2)
        # Calls: 0=MERGE Trip, 1=SELECT trip_id, 2=INSERT DrivingInsightsTrip, 3=SELECT @@IDENTITY
        di_params = _get_call_params(etl_with_cursor.cursor, 2)
        # params order: sid, trip_id, uid, canonical_id, smooth, focus, legal, cwm, overall,
        #               harsh_braking, harsh_turning, harsh_acceleration, wrong_way, attention,
        #               distance, occupant_role, transport_tags_json
        assert di_params[4] == 0.858   # smooth_score
        assert di_params[5] == 0.590   # focus_score
        assert di_params[6] == 0.942   # legal_score
        assert di_params[7] == 1.0     # call_while_moving_score
        assert di_params[8] == 0.797   # overall_score
        assert di_params[9] == 0.900   # harsh_braking_score
        assert di_params[10] == 1.0    # harsh_turning_score
        assert di_params[11] == 0.950  # harsh_acceleration_score
        assert di_params[12] is None   # wrong_way_driving_score (absent → None)
        assert di_params[13] == 0.847  # attention_score

    def test_transport_fields_extracted(self, etl_with_cursor, payload):
        etl_with_cursor.process_driving_insights(sid=1, uid="user-1", payload=payload)
        di_params = _get_call_params(etl_with_cursor.cursor, 2)
        assert di_params[14] == 5399        # distance_meters
        assert di_params[15] == "DRIVER"    # occupant_role

    def test_transport_tags_are_compressed(self, etl_with_cursor, payload):
        etl_with_cursor.process_driving_insights(sid=1, uid="user-1", payload=payload)
        di_params = _get_call_params(etl_with_cursor.cursor, 2)
        # transportTags is an empty dict → falsy → None
        assert di_params[16] is None

    def test_harsh_events_inserted_per_entry(self, etl_with_cursor, payload):
        """Each harshDrivingEvents entry generates one INSERT."""
        payload["harshDrivingEvents"] = [
            {
                "startTime": "2026-04-01T10:05:00Z",
                "startTimeEpoch": 1743503100000,
                "endTime": "2026-04-01T10:05:02Z",
                "endTimeEpoch": 1743503102000,
                "magnitude": 0.75,
                "confidence": 0.90,
                "type": "HARSH_BRAKING",
                "waypoints": [],
            }
        ]
        etl_with_cursor.process_driving_insights(sid=1, uid="user-1", payload=payload)
        all_sqls = [c.args[0] for c in etl_with_cursor.cursor.execute.call_args_list]
        harsh_inserts = [s for s in all_sqls if "DrivingInsightsHarshEvent" in s and "INSERT" in s]
        assert len(harsh_inserts) == 1

    def test_harsh_event_type_extracted(self, etl_with_cursor, payload):
        """The 'type' field from harshDrivingEvent maps to harsh_type column."""
        payload["harshDrivingEvents"] = [{
            "startTime": "2026-04-01T10:05:00Z",
            "startTimeEpoch": 1743503100000,
            "endTime": "2026-04-01T10:05:02Z",
            "endTimeEpoch": 1743503102000,
            "magnitude": 0.75,
            "confidence": 0.90,
            "type": "HARSH_ACCELERATION",
            "waypoints": [],
        }]
        etl_with_cursor.process_driving_insights(sid=1, uid="user-1", payload=payload)
        # Harsh event INSERT is after: MERGE, SELECT trip_id, DI INSERT, @@IDENTITY
        harsh_params = _get_call_params(etl_with_cursor.cursor, 4)
        assert harsh_params[8] == "HARSH_ACCELERATION"  # harsh_type


# ---------------------------------------------------------------------------
# process_user_context (Listener mode)
# ---------------------------------------------------------------------------

class TestProcessUserContextListenerParams:

    @pytest.fixture
    def payload(self):
        return {
            "criteria": ["IN_TRANSPORT_ENDED", "SEGMENT_STARTED"],
            "userContext": {
                "semanticTime": "MORNING",
                "lastKnownLocation": {
                    "latitude": -34.55437,
                    "longitude": -58.48303,
                    "accuracy": 9.0,
                },
                "home": None,
                "work": None,
                "activeSegments": [],
                "events": [],
            },
        }

    def test_semantic_time_extracted(self, etl_with_cursor, payload):
        etl_with_cursor.process_user_context(sid=5, uid="user-2", payload=payload, is_manual=False)
        header_params = _get_call_params(etl_with_cursor.cursor, 0)
        # params: sdk_source_event_id, sentiance_user_id, context_source_type, semantic_time,
        #         latitude, longitude, accuracy
        assert header_params[3] == "MORNING"

    def test_location_extracted(self, etl_with_cursor, payload):
        etl_with_cursor.process_user_context(sid=5, uid="user-2", payload=payload, is_manual=False)
        header_params = _get_call_params(etl_with_cursor.cursor, 0)
        assert header_params[4] == -34.55437   # latitude
        assert header_params[5] == -58.48303   # longitude
        assert header_params[6] == 9.0         # accuracy

    def test_listener_source_type(self, etl_with_cursor, payload):
        etl_with_cursor.process_user_context(sid=5, uid="user-2", payload=payload, is_manual=False)
        header_params = _get_call_params(etl_with_cursor.cursor, 0)
        assert header_params[2] == "LISTENER"

    def test_criteria_codes_inserted(self, etl_with_cursor, payload):
        etl_with_cursor.process_user_context(sid=5, uid="user-2", payload=payload, is_manual=False)
        all_sqls = [c.args[0] for c in etl_with_cursor.cursor.execute.call_args_list]
        criteria_inserts = [s for s in all_sqls if "UserContextUpdateCriteria" in s]
        assert len(criteria_inserts) == 2  # one per criteria code

    def test_criteria_values_passed_correctly(self, etl_with_cursor, payload):
        etl_with_cursor.process_user_context(sid=5, uid="user-2", payload=payload, is_manual=False)
        calls = _execute_calls(etl_with_cursor.cursor)
        criteria_calls = [(sql, params) for sql, params in calls if "UserContextUpdateCriteria" in sql]
        codes = [p[1] for _, p in criteria_calls]
        assert "IN_TRANSPORT_ENDED" in codes
        assert "SEGMENT_STARTED" in codes


class TestProcessUserContextManualParams:

    @pytest.fixture
    def payload(self):
        """requestUserContext payload: the context IS the root, no 'userContext' key."""
        return {
            "semanticTime": "AFTERNOON",
            "lastKnownLocation": {"latitude": -34.60, "longitude": -58.40, "accuracy": 15.0},
            "home": None,
            "work": None,
            "activeSegments": [],
            "events": [],
        }

    def test_manual_source_type(self, etl_with_cursor, payload):
        etl_with_cursor.process_user_context(sid=6, uid="user-3", payload=payload, is_manual=True)
        header_params = _get_call_params(etl_with_cursor.cursor, 0)
        assert header_params[2] == "MANUAL"

    def test_manual_criteria_is_fixed_string(self, etl_with_cursor, payload):
        """Manual requests always insert 'MANUAL_REQUEST' as the criteria code."""
        etl_with_cursor.process_user_context(sid=6, uid="user-3", payload=payload, is_manual=True)
        calls = _execute_calls(etl_with_cursor.cursor)
        criteria_calls = [(sql, params) for sql, params in calls if "UserContextUpdateCriteria" in sql]
        assert len(criteria_calls) == 1
        assert criteria_calls[0][1][1] == "MANUAL_REQUEST"


# ---------------------------------------------------------------------------
# process_crash_event
# ---------------------------------------------------------------------------

class TestProcessCrashEventParams:

    @pytest.fixture
    def payload(self):
        return {
            "time": 1743504600000,
            "location": {
                "latitude": -34.612,
                "longitude": -58.392,
                "accuracy": 5.0,
                "altitude": 25.0,
            },
            "magnitude": 2.35,
            "speedAtImpact": 22.5,
            "deltaV": 18.3,
            "confidence": 0.91,
            "severity": "HIGH",
            "detectorMode": "ACTIVE",
            "precedingLocations": [{"lat": -34.61, "lng": -58.39}],
        }

    def test_crash_time_extracted(self, etl_with_cursor, payload):
        etl_with_cursor.process_crash_event(sid=10, uid="user-4", payload=payload)
        params = _get_call_params(etl_with_cursor.cursor, 0)
        assert params[2] == 1743504600000  # crash_time_epoch

    def test_location_destructured(self, etl_with_cursor, payload):
        etl_with_cursor.process_crash_event(sid=10, uid="user-4", payload=payload)
        params = _get_call_params(etl_with_cursor.cursor, 0)
        assert params[3] == -34.612  # latitude
        assert params[4] == -58.392  # longitude
        assert params[5] == 5.0      # accuracy
        assert params[6] == 25.0     # altitude

    def test_safety_metrics_extracted(self, etl_with_cursor, payload):
        etl_with_cursor.process_crash_event(sid=10, uid="user-4", payload=payload)
        params = _get_call_params(etl_with_cursor.cursor, 0)
        assert params[7] == 2.35    # magnitude
        assert params[8] == 22.5    # speed_at_impact
        assert params[9] == 18.3    # delta_v
        assert params[10] == 0.91   # confidence
        assert params[11] == "HIGH" # severity

    def test_preceding_locations_compressed(self, etl_with_cursor, payload):
        etl_with_cursor.process_crash_event(sid=10, uid="user-4", payload=payload)
        params = _get_call_params(etl_with_cursor.cursor, 0)
        blob = params[13]  # preceding_locations_json
        decompressed = _decompress(blob)
        assert decompressed == payload["precedingLocations"]

    def test_missing_location_fields_are_none(self, etl_with_cursor):
        payload = {
            "time": 999,
            "location": {},  # no lat/lng/accuracy/altitude
            "precedingLocations": None,
        }
        etl_with_cursor.process_crash_event(sid=11, uid="user-5", payload=payload)
        params = _get_call_params(etl_with_cursor.cursor, 0)
        assert params[3] is None  # latitude
        assert params[4] is None  # longitude


# ---------------------------------------------------------------------------
# process_sdk_status
# ---------------------------------------------------------------------------

class TestProcessSdkStatusParams:

    @pytest.fixture
    def payload(self):
        return {
            "startStatus": "STARTED",
            "detectionStatus": "ENABLED_AND_DETECTING",
            "locationPermission": "ALWAYS",
            "isPreciseLocationPermGranted": True,
            "isLocationAvailable": True,
            "wifiQuotaStatus": "SUFFICIENT",
            "mobileQuotaStatus": "SUFFICIENT",
            "diskQuotaStatus": "SUFFICIENT",
            "canDetect": True,
        }

    def test_status_fields_extracted(self, etl_with_cursor, payload):
        etl_with_cursor.process_sdk_status(sid=20, uid="user-6", payload=payload)
        params = _get_call_params(etl_with_cursor.cursor, 0)
        assert params[2] == "STARTED"
        assert params[3] == "ENABLED_AND_DETECTING"
        assert params[4] == "ALWAYS"

    def test_boolean_fields_coerced_to_int(self, etl_with_cursor, payload):
        """BIT columns require integer 0/1, not Python bool."""
        etl_with_cursor.process_sdk_status(sid=20, uid="user-6", payload=payload)
        params = _get_call_params(etl_with_cursor.cursor, 0)
        assert params[5] == 1   # precise_location_granted (True → 1)
        assert params[6] == 1   # is_location_available (True → 1)
        assert params[10] == 1  # can_detect (True → 1)

    def test_false_booleans_coerced_to_zero(self, etl_with_cursor):
        payload = {
            "startStatus": "STOPPED",
            "detectionStatus": "DISABLED",
            "locationPermission": "NEVER",
            "isPreciseLocationPermGranted": False,
            "isLocationAvailable": False,
            "wifiQuotaStatus": "EXCEEDED",
            "mobileQuotaStatus": "EXCEEDED",
            "diskQuotaStatus": "EXCEEDED",
            "canDetect": False,
        }
        etl_with_cursor.process_sdk_status(sid=21, uid="user-7", payload=payload)
        params = _get_call_params(etl_with_cursor.cursor, 0)
        assert params[5] == 0   # precise_location_granted
        assert params[6] == 0   # is_location_available
        assert params[10] == 0  # can_detect


# ---------------------------------------------------------------------------
# process_metadata
# ---------------------------------------------------------------------------

class TestProcessMetadataParams:

    def test_label_and_value_extracted(self, etl_with_cursor):
        payload = {"label": "license_plate", "value": "ABC-123"}
        etl_with_cursor.process_metadata(uid="user-8", payload=payload)
        params = _get_call_params(etl_with_cursor.cursor, 0)
        assert params[1] == "license_plate"  # label
        assert params[2] == "ABC-123"        # value (cast to str)

    def test_numeric_value_cast_to_str(self, etl_with_cursor):
        """value is stored as NVARCHAR(MAX), so it must be str-cast."""
        payload = {"label": "risk_score", "value": 42}
        etl_with_cursor.process_metadata(uid="user-9", payload=payload)
        params = _get_call_params(etl_with_cursor.cursor, 0)
        assert params[2] == "42"
        assert isinstance(params[2], str)

    def test_boolean_value_cast_to_str(self, etl_with_cursor):
        payload = {"label": "verified", "value": True}
        etl_with_cursor.process_metadata(uid="user-10", payload=payload)
        params = _get_call_params(etl_with_cursor.cursor, 0)
        assert params[2] == "True"


# ---------------------------------------------------------------------------
# process_timeline_events
# ---------------------------------------------------------------------------

class TestProcessTimelineEventsParams:

    @pytest.fixture
    def timeline_payload(self):
        return {
            "events": [
                {
                    "id": "evt-001",
                    "type": "IN_TRANSPORT",
                    "startTime": "2026-04-01T08:00:00.000Z",
                    "startTimeEpoch": 1743494400000,
                    "lastUpdateTime": "2026-04-01T08:30:00.000Z",
                    "lastUpdateTimeEpoch": 1743496200000,
                    "endTime": "2026-04-01T08:30:00.000Z",
                    "endTimeEpoch": 1743496200000,
                    "durationInSeconds": 1800,
                    "isProvisional": True,
                    "transportMode": "CAR",
                    "distance": 3200,
                    "occupantRole": "DRIVER",
                    "transportTags": {},
                    "location": {"latitude": -34.60, "longitude": -58.40, "accuracy": 12.0},
                    "venue": None,
                }
            ]
        }

    def test_event_type_extracted(self, etl_with_cursor, timeline_payload):
        etl_with_cursor.process_timeline_events(sid=30, uid="user-11", payload=timeline_payload)
        params = _get_call_params(etl_with_cursor.cursor, 0)
        assert params[3] == "IN_TRANSPORT"   # event_type

    def test_is_provisional_coerced(self, etl_with_cursor, timeline_payload):
        etl_with_cursor.process_timeline_events(sid=30, uid="user-11", payload=timeline_payload)
        params = _get_call_params(etl_with_cursor.cursor, 0)
        assert params[11] == 1  # is_provisional: True → 1

    def test_location_destructured(self, etl_with_cursor, timeline_payload):
        etl_with_cursor.process_timeline_events(sid=30, uid="user-11", payload=timeline_payload)
        params = _get_call_params(etl_with_cursor.cursor, 0)
        assert params[16] == -34.60  # location_latitude
        assert params[17] == -58.40  # location_longitude
        assert params[18] == 12.0    # location_accuracy

    def test_missing_venue_does_not_crash(self, etl_with_cursor, timeline_payload):
        """venue=None must not raise AttributeError."""
        timeline_payload["events"][0]["venue"] = None
        etl_with_cursor.process_timeline_events(sid=30, uid="user-11", payload=timeline_payload)
        params = _get_call_params(etl_with_cursor.cursor, 0)
        assert params[19] is None  # venue_significance
        assert params[20] is None  # venue_type

    def test_in_transport_triggers_upsert_trip(self, etl_with_cursor, timeline_payload):
        """Events with type=IN_TRANSPORT must also trigger upsert_trip (MERGE Trip)."""
        etl_with_cursor.process_timeline_events(sid=30, uid="user-11", payload=timeline_payload)
        all_sqls = [c.args[0] for c in etl_with_cursor.cursor.execute.call_args_list]
        merge_calls = [s for s in all_sqls if "MERGE Trip" in s]
        assert len(merge_calls) == 1

    def test_list_payload_format_also_supported(self, etl_with_cursor, timeline_payload):
        """process_timeline_events accepts both {'events': [...]} and [...] directly."""
        events_list = timeline_payload["events"]
        etl_with_cursor.process_timeline_events(sid=31, uid="user-12", payload=events_list)
        all_sqls = [c.args[0] for c in etl_with_cursor.cursor.execute.call_args_list]
        timeline_inserts = [s for s in all_sqls if "TimelineEventHistory" in s and "INSERT" in s]
        assert len(timeline_inserts) == 1
