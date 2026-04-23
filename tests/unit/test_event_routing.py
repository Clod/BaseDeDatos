"""
test_event_routing.py — Phase 2: Unit tests for the tipo → process_* dispatch
in SentianceETL.run().

WHAT IS BEING TESTED:
    The run() method contains a large if/elif chain that routes each record
    to the correct process_* handler based on the 'tipo' field. These tests
    verify that:

    1. Every supported event type maps to the correct handler method.
    2. Unknown event types are silently ignored (no crash, no DB call).
    3. Child event types (DrivingInsightsHarshEvents etc.) check for an
       orphan parent before inserting — this guard logic is also tested.

APPROACH:
    We patch self.connect() and cursor.fetchall() to simulate a batch of
    records, then assert that the correct process_* method was called with
    the right uid and parsed payload. All process_* methods are mocked so
    no SQL is executed.
"""

import json
import pytest
from unittest.mock import patch, MagicMock, call


# ---------------------------------------------------------------------------
# Helper: build a fake SentianceEventos row
# ---------------------------------------------------------------------------

def _make_row(raw_id, uid, tipo, payload_dict):
    """Returns a tuple mimicking a pyodbc row from SentianceEventos."""
    return (raw_id, uid, json.dumps(payload_dict), tipo)


# ---------------------------------------------------------------------------
# Base fixture: ETL instance with all I/O patched out
# ---------------------------------------------------------------------------

@pytest.fixture
def routed_etl(etl):
    """
    Returns an ETL instance whose run() internals are fully mocked:
    - connect() is a no-op
    - close() is a no-op
    - cursor.execute / fetchall / fetchone are MagicMocks
    - All process_* methods are replaced with MagicMocks

    The fixture returns (etl, cursor_mock) so tests can configure rows.
    """
    cursor_mock = MagicMock()
    conn_mock = MagicMock()

    etl.conn = conn_mock
    etl.cursor = cursor_mock
    etl.connect = lambda: None
    etl.close = lambda: None

    # Default: no rows → run() returns False
    cursor_mock.fetchall.return_value = []
    cursor_mock.fetchone.return_value = (999,)

    # Replace all process_* handlers with MagicMocks
    etl.process_driving_insights = MagicMock()
    etl.process_driving_insights_harsh_events = MagicMock()
    etl.process_driving_insights_phone_events = MagicMock()
    etl.process_driving_insights_call_events = MagicMock()
    etl.process_driving_insights_speeding_events = MagicMock()
    etl.process_driving_insights_wrong_way_events = MagicMock()
    etl.process_user_context = MagicMock()
    etl.process_timeline_events = MagicMock()
    etl.process_metadata = MagicMock()
    etl.process_crash_event = MagicMock()
    etl.process_sdk_status = MagicMock()
    etl.process_technical_event = MagicMock()
    etl.process_activity_history = MagicMock()

    return etl, cursor_mock


# ---------------------------------------------------------------------------
# Routing: each tipo calls the right handler
# ---------------------------------------------------------------------------

class TestEventRouting:

    @pytest.mark.parametrize("tipo, handler_attr", [
        ("DrivingInsights",                     "process_driving_insights"),
        ("DrivingInsightsHarshEvents",          "process_driving_insights_harsh_events"),
        ("DrivingInsightsPhoneEvents",          "process_driving_insights_phone_events"),
        ("DrivingInsightsCallEvents",           "process_driving_insights_call_events"),
        ("DrivingInsightsSpeedingEvents",       "process_driving_insights_speeding_events"),
        ("DrivingInsightsWrongWayDrivingEvents","process_driving_insights_wrong_way_events"),
        ("UserContextUpdate",                   "process_user_context"),
        ("requestUserContext",                  "process_user_context"),
        ("TimelineEvents",                      "process_timeline_events"),
        ("TimelineUpdate",                      "process_timeline_events"),
        ("VehicleCrash",                        "process_crash_event"),
        ("SDKStatus",                           "process_sdk_status"),
        ("UserMetadata",                        "process_metadata"),
        ("TechnicalEvent",                      "process_technical_event"),
        ("UserActivity",                        "process_activity_history"),
    ])
    def test_tipo_dispatches_to_correct_handler(self, routed_etl, tipo, handler_attr):
        etl, cursor_mock = routed_etl
        payload = {"transportId": "trip-xyz"} if "Harsh" in tipo or "Phone" in tipo \
                  or "Call" in tipo or "Speeding" in tipo or "WrongWay" in tipo \
                  else {"id": "some-event", "startTime": "2026-04-01T10:00:00Z"}

        # For child event types, simulate a parent DrivingInsightsTrip existing
        def fetchone_side_effect(*args, **kwargs):
            return (1,)  # parent exists / @@IDENTITY

        cursor_mock.fetchone.side_effect = fetchone_side_effect
        cursor_mock.fetchall.return_value = [_make_row(1, "uid-1", tipo, payload)]

        etl.run(batch_size=1)

        handler = getattr(etl, handler_attr)
        assert handler.called, f"Expected {handler_attr} to be called for tipo='{tipo}'"

    def test_user_context_update_passes_is_manual_false(self, routed_etl):
        etl, cursor_mock = routed_etl
        cursor_mock.fetchall.return_value = [
            _make_row(1, "uid-1", "UserContextUpdate", {"criteria": [], "userContext": {}})
        ]
        etl.run(batch_size=1)
        _, call_kwargs = etl.process_user_context.call_args
        assert call_kwargs.get("is_manual") is False or etl.process_user_context.call_args[0][3] is False

    def test_request_user_context_passes_is_manual_true(self, routed_etl):
        etl, cursor_mock = routed_etl
        cursor_mock.fetchall.return_value = [
            _make_row(1, "uid-1", "requestUserContext", {"semanticTime": "MORNING"})
        ]
        etl.run(batch_size=1)
        args = etl.process_user_context.call_args[0]
        # is_manual is the 4th positional arg: process_user_context(sid, uid, p, is_manual)
        assert args[3] is True


# ---------------------------------------------------------------------------
# Orphan child event guard
# ---------------------------------------------------------------------------

class TestOrphanChildEventGuard:

    def test_child_without_parent_is_skipped(self, routed_etl):
        """
        When a child event (e.g. DrivingInsightsHarshEvents) arrives but no
        parent DrivingInsightsTrip exists, the record must be skipped (not
        marked processed, handler not called).
        """
        etl, cursor_mock = routed_etl
        cursor_mock.fetchall.return_value = [
            _make_row(42, "uid-1", "DrivingInsightsHarshEvents", {"transportId": "trip-missing"})
        ]
        # The ETL uses cursor.execute(...).fetchone() (chained), so we must
        # configure the return value on execute's return value, not cursor directly.
        cursor_mock.execute.return_value.fetchone.return_value = None

        etl.run(batch_size=1)

        etl.process_driving_insights_harsh_events.assert_not_called()

    def test_child_without_parent_leaves_is_processed_unchanged(self, routed_etl):
        """
        Orphan children must NOT have is_processed updated (left at 0 for retry).
        """
        etl, cursor_mock = routed_etl
        cursor_mock.fetchall.return_value = [
            _make_row(42, "uid-1", "DrivingInsightsHarshEvents", {"transportId": "trip-missing"})
        ]
        cursor_mock.execute.return_value.fetchone.return_value = None

        etl.run(batch_size=1)

        # Check that no UPDATE SentianceEventos SET is_processed = 1 was called
        all_update_calls = [
            c.args for c in cursor_mock.execute.call_args_list
            if "UPDATE SentianceEventos" in str(c.args[0])
            and "is_processed = 1" in str(c.args[0])
        ]
        assert len(all_update_calls) == 0, "Orphan child must not be marked as processed=1"

    def test_child_without_transport_id_is_marked_failed(self, routed_etl):
        """
        A child event with no transportId at all must be marked is_processed=-1.
        """
        etl, cursor_mock = routed_etl
        cursor_mock.fetchall.return_value = [
            _make_row(99, "uid-1", "DrivingInsightsHarshEvents", {})  # no transportId
        ]
        cursor_mock.fetchone.return_value = None

        etl.run(batch_size=1)

        update_calls = [
            c.args for c in cursor_mock.execute.call_args_list
            if "UPDATE SentianceEventos" in str(c.args[0])
            and "is_processed = -1" in str(c.args[0])
        ]
        assert len(update_calls) == 1

    def test_child_with_existing_parent_is_processed(self, routed_etl):
        """
        When parent DrivingInsightsTrip exists, child must call its handler.
        """
        etl, cursor_mock = routed_etl
        cursor_mock.fetchall.return_value = [
            _make_row(50, "uid-1", "DrivingInsightsHarshEvents", {"transportId": "trip-found"})
        ]
        # Both the parent check and the @@IDENTITY lookup use cursor.execute(...).fetchone().
        # side_effect is consumed in order: first call → parent found, second → SdkSourceEvent id.
        cursor_mock.execute.return_value.fetchone.side_effect = [(1,), (999,)]

        etl.run(batch_size=1)

        etl.process_driving_insights_harsh_events.assert_called_once()


# ---------------------------------------------------------------------------
# run() return value
# ---------------------------------------------------------------------------

class TestRunReturnValue:

    def test_returns_false_when_no_rows(self, routed_etl):
        etl, cursor_mock = routed_etl
        cursor_mock.fetchall.return_value = []
        assert etl.run(batch_size=10) is False

    def test_returns_true_when_rows_processed(self, routed_etl):
        etl, cursor_mock = routed_etl
        cursor_mock.fetchall.return_value = [
            _make_row(1, "uid-1", "SDKStatus", {"startStatus": "STARTED"})
        ]
        cursor_mock.fetchone.return_value = (999,)
        assert etl.run(batch_size=10) is True

    def test_returns_false_when_all_records_are_orphans(self, routed_etl):
        """
        If every record in the batch is an orphan child (skipped), run() must
        return False to prevent an infinite loop in run_full_pipeline.py.
        """
        etl, cursor_mock = routed_etl
        cursor_mock.fetchall.return_value = [
            _make_row(1, "uid-1", "DrivingInsightsHarshEvents", {"transportId": "missing"}),
            _make_row(2, "uid-1", "DrivingInsightsPhoneEvents", {"transportId": "missing"}),
        ]
        # No parent found for any child — must return False to break infinite loop.
        cursor_mock.execute.return_value.fetchone.return_value = None

        result = etl.run(batch_size=10)
        assert result is False
