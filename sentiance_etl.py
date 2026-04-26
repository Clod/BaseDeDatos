"""
SENTIANCE SDK DATA ETL ENGINE
=============================

DESCRIPTION:
This script implements a high-performance, two-stage data pipeline designed
to transform raw Sentiance SDK telemetry into a structured relational domain model.
It handles 15+ different data points including safety scores, mobility segments,
historical timelines, and crash detection.

PURPOSE/WHY:
- Compliance: Mirrors the 'Entregable.md' and 'MapeoSDK_BD.md' specifications.
- Analytics: Enables SQL-based analysis of driving behavior and user mobility.
- Efficiency: Implements GZIP compression for volumetric data (waypoints).
- Robustness: Captures and isolates processing failures in a forensic shadow table.

WORKFLOW:
1. Extraction: Queries 'SentianceEventos' for unprocessed raw JSON records.
2. Deduplication: Generates a SHA-256 hash to ensure unique payload processing.
3. Transformation:
   - Normalizes UserContext formats (Manual vs. Listener).
   - Aggressively discovers journeys (Trips) across all event types.
   - Truncates timestamps to DATETIME2(3) precision.
4. Load: Executes atomic MERGE/INSERT operations across the domain tables.
5. Finalization: Marks original records as processed (1) or failed (-1).

PREREQUISITES:
- Python 3.10+
- System: unixODBC (Mac: brew install unixodbc)
- Driver: Microsoft ODBC Driver 18 for SQL Server
- Environment:
  - .venv (managed by uv or pip)
  - .env (containing DB_SERVER, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME)

USAGE:
Single Batch Execution:
    python sentiance_etl.py

Continuous Queue Processing:
    python run_full_pipeline.py

AUTHOR: Claudio Grasso / AI Assistant
DATE: April 2026
"""

import os
import json
import gzip
import pyodbc
import hashlib
import logging
import traceback
from datetime import datetime
from dotenv import load_dotenv

# Load database credentials from the local .env file
load_dotenv()

# Configure logging for production-grade operational monitoring
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("sentiance_etl.log"),
    ],
)
logger = logging.getLogger("SentianceETL")


class SentianceETL:
    """
    Main ETL engine for the Sentiance SDK data pipeline.

    Transforms raw JSON payloads stored in SentianceEventos into a normalised
    relational domain model across 15+ tables. Each payload type is routed to a
    dedicated process_* method that performs the necessary INSERT / MERGE
    operations and marks the source record as processed.

    Typical lifecycle per batch:
        etl = SentianceETL()
        etl.run(batch_size=500)   # opens, processes, commits, closes
    """

    def __init__(self):
        """Reads database credentials from environment variables and builds the ODBC connection string.

        Reads: DB_SERVER, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME from the
        environment (loaded via python-dotenv from .env).

        Raises:
            ValueError: if any of the five required environment variables is missing.
        """
        server, port, user, pwd, db = (
            os.getenv("DB_SERVER"),
            os.getenv("DB_PORT"),
            os.getenv("DB_USER"),
            os.getenv("DB_PASSWORD"),
            os.getenv("DB_NAME"),
        )
        if not all([server, port, user, pwd, db]):
            raise ValueError("Missing database configuration in .env")
        self.conn_str = f"DRIVER={{ODBC Driver 18 for SQL Server}};SERVER={server},{port};DATABASE={db};UID={user};PWD={pwd};Encrypt=yes;TrustServerCertificate=yes"
        self.conn, self.cursor = None, None

    def connect(self):
        """Opens a new pyodbc connection and assigns self.conn and self.cursor.

        Called once at the start of each run() invocation. Use reconnect()
        instead if a live connection needs to be replaced after an error.
        """
        self.conn = pyodbc.connect(self.conn_str)
        self.cursor = self.conn.cursor()

    def reconnect(self):
        """Closes the current connection (ignoring errors) and opens a fresh one.

        Called from the error handler inside run() when a pyodbc connection is
        found to be dead after a failed commit/rollback. Replaces self.conn and
        self.cursor so the next record in the batch can be attempted cleanly.
        """
        try:
            if self.conn:
                self.conn.close()
        except Exception:
            pass
        self.conn = pyodbc.connect(self.conn_str)
        self.cursor = self.conn.cursor()

    def close(self):
        """Closes the database connection if one is open.

        Called in the finally block of run() to guarantee the connection is
        released even when an unhandled exception propagates out of the batch loop.
        """
        if self.conn:
            self.conn.close()

    def format_ts(self, ts_str):
        """Converts an ISO 8601 timestamp string to the SQL Server DATETIME2(3) text format.

        Strips the trailing 'Z' (UTC marker), replaces the 'T' separator with a
        space, and truncates to 23 characters (YYYY-MM-DD HH:MM:SS.mmm). This
        matches the precision accepted by DATETIME2(3) without requiring a cast
        inside the SQL statement.

        Args:
            ts_str: ISO 8601 string such as "2026-04-21T15:04:23.824-0300" or
                    "2026-04-21T15:04:23.824Z". None or empty string is allowed.

        Returns:
            Formatted string "YYYY-MM-DD HH:MM:SS.mmm", or None if ts_str is falsy.
        """
        if not ts_str:
            return None
        return ts_str.replace("Z", "").replace("T", " ")[:23]

    def compress_data(self, data):
        """Serialises a Python object to JSON and compresses it with GZIP.

        Used to store high-cardinality arrays (waypoints, transportTags) in
        VARBINARY(MAX) columns, reducing row size significantly compared to
        plain JSON text.

        Args:
            data: any JSON-serialisable value (dict, list, etc.). None or empty
                  values short-circuit immediately without allocating.

        Returns:
            bytes: GZIP-compressed UTF-8 JSON, or None if data is falsy.
        """
        if not data:
            return None
        return gzip.compress(json.dumps(data).encode("utf-8"))

    def get_hash(self, text):
        """Computes a SHA-256 hex digest of a string for payload deduplication.

        The digest is stored in SdkSourceEvent.payload_hash. A duplicate hash
        indicates the exact same raw JSON was already submitted, which can happen
        when the mobile app retries a failed webhook delivery.

        Args:
            text: the raw JSON string of the payload.

        Returns:
            str: 64-character lowercase hexadecimal SHA-256 digest.
        """
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def log_error_to_db(self, raw_id, uid, tipo, json_str, err):
        """Persists a processing failure to the SentianceEventos_Errors shadow table.

        Called after a rollback inside the run() error handler. The insert is
        attempted on a best-effort basis: any secondary failure is silently
        swallowed to avoid masking the original error. This table serves as a
        forensic audit trail for records that could not be processed.

        Args:
            raw_id: SentianceEventos.id of the failed record.
            uid:    Sentiance user ID associated with the record.
            tipo:   payload type string (e.g. 'DrivingInsights').
            json_str: raw JSON string of the original payload.
            err:    formatted traceback string from traceback.format_exc().
        """
        try:
            self.cursor.execute(
                "INSERT INTO SentianceEventos_Errors (original_id, sentiance_user_id, tipo, raw_json, error_message) VALUES (?, ?, ?, ?, ?)",
                (raw_id, uid, tipo, json_str, err),
            )
        except:
            pass

    def upsert_trip(self, sid, uid, transport):
        """Consolidates a finalised transport event into the central Trip table.

        Provisional trips (isProvisional=True) are silently ignored: they carry
        temporary IDs that are never reused by the final event, so storing them
        would pollute the table with unresolvable orphan rows.

        On INSERT, records creating_sdk_source_event_id so the originating ETL
        event is permanently traceable. On UPDATE, records
        last_updated_by_sdk_source_event_id to track the latest enriching event
        (e.g. DrivingInsights arriving after an earlier UserContext upsert).

        Args:
            sid: sdk_source_event_id of the currently-processing SdkSourceEvent row.
            uid: Sentiance user ID (sentiance_user_id).
            transport: dict containing the transport event fields from the payload.

        Returns:
            trip_id (int) if the row was inserted or already existed, None otherwise.
        """
        # Discard provisional trips
        if transport.get("isProvisional"):
            return None
        tid = transport.get("id")
        if not tid:
            return None
        sql = """
        MERGE Trip AS target
        USING (SELECT ? AS tid, ? AS uid) AS source
        ON target.canonical_transport_event_id = source.tid AND target.sentiance_user_id = source.uid
        WHEN MATCHED THEN
            UPDATE SET last_update_time = ?, last_update_time_epoch = ?, end_time = ?, end_time_epoch = ?,
                       duration_in_seconds = ?, distance_meters = ?, transport_mode = ?, occupant_role = ?,
                       is_provisional = ?, last_updated_by_sdk_source_event_id = ?, updated_at = GETDATE()
        WHEN NOT MATCHED THEN
            INSERT (sentiance_user_id, canonical_transport_event_id, first_seen_from, start_time, start_time_epoch,
                    last_update_time, last_update_time_epoch, end_time, end_time_epoch, duration_in_seconds,
                    distance_meters, transport_mode, occupant_role, is_provisional, transport_tags_json,
                    waypoints_json, creating_sdk_source_event_id, last_updated_by_sdk_source_event_id,
                    created_at, updated_at)
            VALUES (?, ?, 'ETL_PROCESS', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE(), GETDATE());
        """
        params = [
            tid,
            uid,
            # WHEN MATCHED
            self.format_ts(transport.get("lastUpdateTime")),
            transport.get("lastUpdateTimeEpoch"),
            self.format_ts(transport.get("endTime")),
            transport.get("endTimeEpoch"),
            transport.get("durationInSeconds"),
            transport.get("distance"),
            transport.get("transportMode"),
            transport.get("occupantRole"),
            1 if transport.get("isProvisional") else 0,
            sid,
            # WHEN NOT MATCHED
            uid,
            tid,
            self.format_ts(transport.get("startTime")),
            transport.get("startTimeEpoch"),
            self.format_ts(transport.get("lastUpdateTime")),
            transport.get("lastUpdateTimeEpoch"),
            self.format_ts(transport.get("endTime")),
            transport.get("endTimeEpoch"),
            transport.get("durationInSeconds"),
            transport.get("distance"),
            transport.get("transportMode"),
            transport.get("occupantRole"),
            1 if transport.get("isProvisional") else 0,
            self.compress_data(transport.get("transportTags")),
            self.compress_data(transport.get("waypoints")),
            sid,
            sid,
        ]
        self.cursor.execute(sql, params)
        res = self.cursor.execute(
            "SELECT trip_id FROM Trip WHERE canonical_transport_event_id = ? AND sentiance_user_id = ?",
            (tid, uid),
        ).fetchone()
        return res[0] if res else None

    def process_driving_insights(self, sid, uid, payload):
        """Processes a completed DrivingInsights event into the domain model.

        Processes a DrivingInsights webhook payload. Per the Sentiance SDK spec,
        this payload contains only 'transportEvent' and 'safetyScores' — no
        inline sub-event arrays. Sub-events (harsh driving, phone usage, speeding,
        calls, wrong-way driving) are fetched separately via explicit SDK calls and
        arrive as distinct SentianceEventos records (tipo = 'DrivingInsightsHarshEvents',
        'DrivingInsightsPhoneEvents', etc.), each routed to their own process_* method.

        Write order:
            1. upsert_trip         → Trip (canonical row, shared with Timeline/UserContext)
            2. DrivingInsightsTrip → links sdk_source_event_id to the Trip row and
                                     stores all safety score columns.

        Note: waypoints are stored exclusively in Trip (via upsert_trip) to
        avoid duplicating GPS coordinates across child tables.

        Args:
            sid: sdk_source_event_id of the current SdkSourceEvent row.
            uid: Sentiance user ID.
            payload: parsed DrivingInsights JSON dict containing
                     'transportEvent', 'safetyScores', and the sub-event arrays.
        """
        transport = payload.get("transportEvent", {})
        scores = payload.get("safetyScores", {})
        trip_id = self.upsert_trip(sid, uid, transport)

        # DrivingInsightsTrip: parent-of-safety-events, FK->Trip, no geo/waypoints
        sql = """INSERT INTO DrivingInsightsTrip (sdk_source_event_id, trip_id, sentiance_user_id, canonical_transport_event_id,
                 smooth_score, focus_score, legal_score, call_while_moving_score, overall_score, harsh_braking_score,
                 harsh_turning_score, harsh_acceleration_score, wrong_way_driving_score, attention_score,
                 distance_meters, occupant_role, transport_tags_json, created_at)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE())"""
        self.cursor.execute(
            sql,
            (
                sid,
                trip_id,
                uid,
                transport.get("id"),
                scores.get("smoothScore"),
                scores.get("focusScore"),
                scores.get("legalScore"),
                scores.get("callWhileMovingScore"),
                scores.get("overallScore"),
                scores.get("harshBrakingScore"),
                scores.get("harshTurningScore"),
                scores.get("harshAccelerationScore"),
                scores.get("wrongWayDrivingScore"),
                scores.get("attentionScore"),
                transport.get("distance"),
                transport.get("occupantRole"),
                self.compress_data(transport.get("transportTags")),
            ),
        )

    def process_driving_insights_harsh_events(self, sid, uid, payload):
        """Stores harsh driving events for a completed trip into DrivingInsightsHarshEvent.

        Harsh events are acceleration, braking, and turning incidents detected
        during the trip. Each carries a magnitude, confidence score, type, and
        a compressed waypoints trail covering the incident interval.

        Resolves the parent DrivingInsightsTrip row via transportId. Silently
        returns if no matching parent is found (parent-guard enforced upstream).

        Args:
            sid: sdk_source_event_id of the current SdkSourceEvent row.
            uid: Sentiance user ID.
            payload: dict with 'transportId' (str) and 'events' (list of HarshDrivingEvent).

        Returns:
            None
        """
        logger.debug(
            f"process_driving_insights_harsh_events called with payload keys: {list(payload.keys())}"
        )
        transport_id = payload.get("transportId")
        if not transport_id:
            logger.warning("No transportId found in payload")
            return
        logger.debug(
            f"Looking up driving_insights_trip_id for transport_id={transport_id} uid={uid}"
        )
        di_res = self.cursor.execute(
            "SELECT driving_insights_trip_id FROM DrivingInsightsTrip WHERE canonical_transport_event_id = ? AND sentiance_user_id = ?",
            (str(transport_id), str(uid)),
        ).fetchone()
        if not di_res:
            logger.warning(
                f"No DrivingInsightsTrip found for transport_id={transport_id}"
            )
            return
        di_trip_id = di_res[0]
        logger.debug(
            f"Found driving_insights_trip_id={di_trip_id}, inserting {len(payload.get('events', []))} events"
        )
        for e in payload.get("events", []):
            self.cursor.execute(
                "INSERT INTO DrivingInsightsHarshEvent (sdk_source_event_id, driving_insights_trip_id, start_time, start_time_epoch, end_time, end_time_epoch, magnitude, confidence, harsh_type, waypoints_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    sid,
                    di_trip_id,
                    self.format_ts(e.get("startTime")),
                    e.get("startTimeEpoch"),
                    self.format_ts(e.get("endTime")),
                    e.get("endTimeEpoch"),
                    e.get("magnitude"),
                    e.get("confidence"),
                    e.get("type"),
                    self.compress_data(e.get("waypoints")),
                ),
            )

    def process_driving_insights_phone_events(self, sid, uid, payload):
        """Stores phone-screen interaction events for a completed trip into DrivingInsightsPhoneEvent.

        Resolves the parent DrivingInsightsTrip row via transportId before inserting.
        Silently returns if the parent does not yet exist (parent-guard is enforced
        upstream in run() before this method is ever called).

        Args:
            sid: sdk_source_event_id of the current SdkSourceEvent row.
            uid: Sentiance user ID.
            payload: dict with 'transportId' (str) and 'events' (list of PhoneUsageEvent).

        Returns:
            None
        """
        transport_id = payload.get("transportId")
        if not transport_id:
            return
        di_res = self.cursor.execute(
            "SELECT driving_insights_trip_id FROM DrivingInsightsTrip WHERE canonical_transport_event_id = ? AND sentiance_user_id = ?",
            (transport_id, uid),
        ).fetchone()
        if not di_res:
            return
        di_trip_id = di_res[0]
        for e in payload.get("events", []):
            self.cursor.execute(
                "INSERT INTO DrivingInsightsPhoneEvent (sdk_source_event_id, driving_insights_trip_id, start_time, start_time_epoch, end_time, end_time_epoch, call_state, waypoints_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    sid,
                    di_trip_id,
                    self.format_ts(e.get("startTime")),
                    e.get("startTimeEpoch"),
                    self.format_ts(e.get("endTime")),
                    e.get("endTimeEpoch"),
                    e.get("callState"),
                    self.compress_data(e.get("waypoints")),
                ),
            )

    def process_driving_insights_call_events(self, sid, uid, payload):
        """Stores call-while-moving events for a completed trip into DrivingInsightsCallEvent.

        Supersedes the deprecated getCallWhileMovingEvents API. Each event
        captures speed range and hands-free state for the duration of the call.

        Args:
            sid: sdk_source_event_id of the current SdkSourceEvent row.
            uid: Sentiance user ID.
            payload: dict with 'transportId' (str) and 'events' (list of CallEvent).

        Returns:
            None
        """
        transport_id = payload.get("transportId")
        if not transport_id:
            return
        di_res = self.cursor.execute(
            "SELECT driving_insights_trip_id FROM DrivingInsightsTrip WHERE canonical_transport_event_id = ? AND sentiance_user_id = ?",
            (transport_id, uid),
        ).fetchone()
        if not di_res:
            return
        di_trip_id = di_res[0]
        for e in payload.get("events", []):
            self.cursor.execute(
                "INSERT INTO DrivingInsightsCallEvent (sdk_source_event_id, driving_insights_trip_id, start_time, start_time_epoch, end_time, end_time_epoch, min_traveled_speed_mps, max_traveled_speed_mps, hands_free_state, waypoints_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    sid,
                    di_trip_id,
                    self.format_ts(e.get("startTime")),
                    e.get("startTimeEpoch"),
                    self.format_ts(e.get("endTime")),
                    e.get("endTimeEpoch"),
                    e.get("minTraveledSpeedMps"),
                    e.get("maxTraveledSpeedMps"),
                    e.get("handsFreeState"),
                    self.compress_data(e.get("waypoints")),
                ),
            )

    def process_driving_insights_speeding_events(self, sid, uid, payload):
        """Stores speed-limit-exceedance intervals for a completed trip into DrivingInsightsSpeedingEvent.

        Args:
            sid: sdk_source_event_id of the current SdkSourceEvent row.
            uid: Sentiance user ID.
            payload: dict with 'transportId' (str) and 'events' (list of SpeedingEvent).

        Returns:
            None
        """
        transport_id = payload.get("transportId")
        if not transport_id:
            return
        di_res = self.cursor.execute(
            "SELECT driving_insights_trip_id FROM DrivingInsightsTrip WHERE canonical_transport_event_id = ? AND sentiance_user_id = ?",
            (transport_id, uid),
        ).fetchone()
        if not di_res:
            return
        di_trip_id = di_res[0]
        for e in payload.get("events", []):
            self.cursor.execute(
                "INSERT INTO DrivingInsightsSpeedingEvent (sdk_source_event_id, driving_insights_trip_id, start_time, start_time_epoch, end_time, end_time_epoch, waypoints_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    sid,
                    di_trip_id,
                    self.format_ts(e.get("startTime")),
                    e.get("startTimeEpoch"),
                    self.format_ts(e.get("endTime")),
                    e.get("endTimeEpoch"),
                    self.compress_data(e.get("waypoints")),
                ),
            )

    def process_driving_insights_wrong_way_events(self, sid, uid, payload):
        """Stores wrong-way driving intervals for a completed trip into DrivingInsightsWrongWayDrivingEvent.

        Args:
            sid: sdk_source_event_id of the current SdkSourceEvent row.
            uid: Sentiance user ID.
            payload: dict with 'transportId' (str) and 'events' (list of WrongWayDrivingEvent).

        Returns:
            None
        """
        transport_id = payload.get("transportId")
        if not transport_id:
            return
        di_res = self.cursor.execute(
            "SELECT driving_insights_trip_id FROM DrivingInsightsTrip WHERE canonical_transport_event_id = ? AND sentiance_user_id = ?",
            (transport_id, uid),
        ).fetchone()
        if not di_res:
            return
        di_trip_id = di_res[0]
        for e in payload.get("events", []):
            self.cursor.execute(
                "INSERT INTO DrivingInsightsWrongWayDrivingEvent (sdk_source_event_id, driving_insights_trip_id, start_time, start_time_epoch, end_time, end_time_epoch, waypoints_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    sid,
                    di_trip_id,
                    self.format_ts(e.get("startTime")),
                    e.get("startTimeEpoch"),
                    self.format_ts(e.get("endTime")),
                    e.get("endTimeEpoch"),
                    self.compress_data(e.get("waypoints")),
                ),
            )

    def process_user_context(self, sid, uid, payload, is_manual=False):
        """Processes a UserContext snapshot into the user-context domain tables.

        Handles two payload shapes:
          - Listener (UserContextUpdate): payload = {"criteria": [...], "userContext": {...}}
          - Manual   (requestUserContext): payload is the context object directly.

        Write order (all keyed by user_context_payload_id from UserContextHeader):
            1. UserContextHeader            → one row per event (semantic time, location).
            2. UserContextUpdateCriteria    → one row per criteria code.
            3. UserHomeHistory / UserWorkHistory → one row each if home/work present.
            4. UserContextActiveSegmentDetail   → one row per active behavioural segment.
            5. UserContextSegmentAttribute      → one row per segment attribute.
            6. UserContextEventDetail           → one row per activity in the events array.
            7. Trip (via upsert_trip)           → one upsert per finalised IN_TRANSPORT event.

        Args:
            sid:       sdk_source_event_id of the current SdkSourceEvent row.
            uid:       Sentiance user ID.
            payload:   parsed JSON dict. Shape depends on is_manual.
            is_manual: True for 'requestUserContext' (payload IS the context);
                       False for 'UserContextUpdate' (context is under 'userContext' key).

        Returns:
            None
        """
        context = payload if is_manual else payload.get("userContext", {})
        criteria = ["MANUAL_REQUEST"] if is_manual else payload.get("criteria", [])
        loc = context.get("lastKnownLocation", {})

        self.cursor.execute(
            "INSERT INTO UserContextHeader (sdk_source_event_id, sentiance_user_id, context_source_type, semantic_time, last_known_latitude, last_known_longitude, last_known_accuracy, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, GETDATE())",
            (
                sid,
                uid,
                "MANUAL" if is_manual else "LISTENER",
                context.get("semanticTime"),
                loc.get("latitude"),
                loc.get("longitude"),
                loc.get("accuracy"),
            ),
        )
        phid = self.cursor.execute("SELECT @@IDENTITY").fetchone()[0]

        for c in criteria:
            self.cursor.execute(
                "INSERT INTO UserContextUpdateCriteria (user_context_payload_id, criteria_code) VALUES (?, ?)",
                (phid, c),
            )

        for sig in ["home", "work"]:
            v = context.get(sig)
            if v:
                vloc = v.get("location", {})
                table = "UserHomeHistory" if sig == "home" else "UserWorkHistory"
                self.cursor.execute(
                    f"INSERT INTO {table} (user_context_payload_id, significance, venue_type, latitude, longitude, accuracy) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        phid,
                        sig.upper(),
                        v.get("type"),
                        vloc.get("latitude"),
                        vloc.get("longitude"),
                        vloc.get("accuracy"),
                    ),
                )

        for s in context.get("activeSegments", []):
            self.cursor.execute(
                "INSERT INTO UserContextActiveSegmentDetail (user_context_payload_id, sentiance_user_id, segment_id, category, subcategory, segment_type, start_time, start_time_epoch, end_time, end_time_epoch, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE())",
                (
                    phid,
                    uid,
                    str(s.get("id")),
                    s.get("category"),
                    s.get("subcategory"),
                    s.get("type"),
                    self.format_ts(s.get("startTime")),
                    s.get("startTimeEpoch"),
                    self.format_ts(s.get("endTime")),
                    s.get("endTimeEpoch"),
                ),
            )
            sh_id = self.cursor.execute("SELECT @@IDENTITY").fetchone()[0]
            for a in s.get("attributes", []):
                self.cursor.execute(
                    "INSERT INTO UserContextSegmentAttribute (user_context_active_segment_detail_id, attribute_name, attribute_value) VALUES (?, ?, ?)",
                    (sh_id, a.get("name"), a.get("value")),
                )

        for e in context.get("events", []):
            self.cursor.execute(
                "INSERT INTO UserContextEventDetail (user_context_payload_id, sentiance_user_id, event_id, event_type, start_time, start_time_epoch, last_update_time, last_update_time_epoch, end_time, end_time_epoch, duration_in_seconds, is_provisional, transport_mode, distance_meters, occupant_role, transport_tags_json, location_latitude, location_longitude, location_accuracy, venue_significance, venue_type, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE())",
                (
                    phid,
                    uid,
                    e.get("id"),
                    e.get("type"),
                    self.format_ts(e.get("startTime")),
                    e.get("startTimeEpoch"),
                    self.format_ts(e.get("lastUpdateTime")),
                    e.get("lastUpdateTimeEpoch"),
                    self.format_ts(e.get("endTime")),
                    e.get("endTimeEpoch"),
                    e.get("durationInSeconds"),
                    1 if e.get("isProvisional") else 0,
                    e.get("transportMode"),
                    e.get("distance"),
                    e.get("occupantRole"),
                    self.compress_data(e.get("transportTags")),
                    (e.get("location") or {}).get("latitude"),
                    (e.get("location") or {}).get("longitude"),
                    (e.get("location") or {}).get("accuracy"),
                    (e.get("venue") or {}).get("significance"),
                    (e.get("venue") or {}).get("type"),
                ),
            )
            if e.get("type") == "IN_TRANSPORT" or e.get("transportMode"):
                self.upsert_trip(sid, uid, e)

    def process_timeline_events(self, sid, uid, payload):
        """Stores a historical activity timeline into TimelineEventHistory.

        Handles two payload shapes accepted by the SDK:
          - Object:  {"events": [...]}  (TimelineEvents / TimelineUpdate webhooks)
          - Array:   [...]              (direct list of events, some integration variants)

        Each event in the array is inserted as one TimelineEventHistory row. Any
        event with type IN_TRANSPORT or a non-null transportMode is also upserted
        into Trip via upsert_trip (provisional events are discarded there).

        Args:
            sid:     sdk_source_event_id of the current SdkSourceEvent row.
            uid:     Sentiance user ID.
            payload: parsed JSON — either a dict with an 'events' key or a list.

        Returns:
            None
        """
        events = payload if isinstance(payload, list) else payload.get("events", [])
        for e in events:
            self.cursor.execute(
                "INSERT INTO TimelineEventHistory (sdk_source_event_id, sentiance_user_id, event_id, event_type, start_time, start_time_epoch, last_update_time, last_update_time_epoch, end_time, end_time_epoch, duration_in_seconds, is_provisional, transport_mode, distance_meters, occupant_role, transport_tags_json, location_latitude, location_longitude, location_accuracy, venue_significance, venue_type, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE())",
                (
                    sid,
                    uid,
                    e.get("id"),
                    e.get("type"),
                    self.format_ts(e.get("startTime")),
                    e.get("startTimeEpoch"),
                    self.format_ts(e.get("lastUpdateTime")),
                    e.get("lastUpdateTimeEpoch"),
                    self.format_ts(e.get("endTime")),
                    e.get("endTimeEpoch"),
                    e.get("durationInSeconds"),
                    1 if e.get("isProvisional") else 0,
                    e.get("transportMode"),
                    e.get("distance"),
                    e.get("occupantRole"),
                    self.compress_data(e.get("transportTags")),
                    (e.get("location") or {}).get("latitude"),
                    (e.get("location") or {}).get("longitude"),
                    (e.get("location") or {}).get("accuracy"),
                    (e.get("venue") or {}).get("significance"),
                    (e.get("venue") or {}).get("type"),
                ),
            )
            if e.get("type") == "IN_TRANSPORT" or e.get("transportMode"):
                self.upsert_trip(sid, uid, e)

    def process_metadata(self, uid, payload):
        """Stores a custom user metadata label-value pair into UserMetadata.

        Metadata records are arbitrary key-value tags set by the host application
        (e.g. vehicle type, driver tier, fleet ID). Multiple records with the same
        label are allowed; deduplication is the responsibility of the consumer.

        Args:
            uid:     Sentiance user ID.
            payload: dict with 'label' (str) and 'value' (any scalar, coerced to str).

        Returns:
            None
        """
        label, val = payload.get("label"), payload.get("value")
        self.cursor.execute(
            "INSERT INTO UserMetadata (sentiance_user_id, label, value, updated_at) VALUES (?, ?, ?, GETDATE())",
            (uid, label, str(val)),
        )

    def process_crash_event(self, sid, uid, payload):
        """Stores a vehicle crash detection event into VehicleCrashEvent.

        Captures all telemetry emitted by the Sentiance crash detector: GPS
        location at impact, accelerometer-derived magnitude and delta-V, speed,
        confidence, severity classification, and the preceding GPS trail
        (compressed as GZIP JSON for storage efficiency).

        Args:
            sid:     sdk_source_event_id of the current SdkSourceEvent row.
            uid:     Sentiance user ID.
            payload: parsed VehicleCrash JSON dict.

        Returns:
            None
        """
        l = payload.get("location", {})
        self.cursor.execute(
            "INSERT INTO VehicleCrashEvent (sdk_source_event_id, sentiance_user_id, crash_time_epoch, latitude, longitude, accuracy, altitude, magnitude, speed_at_impact, delta_v, confidence, severity, detector_mode, preceding_locations_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                sid,
                uid,
                payload.get("time"),
                l.get("latitude"),
                l.get("longitude"),
                l.get("accuracy"),
                l.get("altitude"),
                payload.get("magnitude"),
                payload.get("speedAtImpact"),
                payload.get("deltaV"),
                payload.get("confidence"),
                payload.get("severity"),
                payload.get("detectorMode"),
                self.compress_data(payload.get("precedingLocations")),
            ),
        )

    def process_sdk_status(self, sid, uid, payload):
        """Stores an SDK health snapshot into SdkStatusHistory.

        Records the operational state of the Sentiance SDK on the device at a
        point in time: detection and start statuses, location permission level,
        data quota consumption (WiFi / mobile / disk), and whether the SDK is
        capable of active detection. Useful for diagnosing gaps in data coverage.

        Args:
            sid:     sdk_source_event_id of the current SdkSourceEvent row.
            uid:     Sentiance user ID.
            payload: parsed SDKStatus JSON dict.

        Returns:
            None
        """
        self.cursor.execute(
            "INSERT INTO SdkStatusHistory (sdk_source_event_id, sentiance_user_id, start_status, detection_status, location_permission, precise_location_granted, is_location_available, quota_status_wifi, quota_status_mobile, quota_status_disk, can_detect, captured_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE())",
            (
                sid,
                uid,
                payload.get("startStatus"),
                payload.get("detectionStatus"),
                payload.get("locationPermission"),
                1 if payload.get("isPreciseLocationPermGranted") else 0,
                1 if payload.get("isLocationAvailable") else 0,
                payload.get("wifiQuotaStatus"),
                payload.get("mobileQuotaStatus"),
                payload.get("diskQuotaStatus"),
                1 if payload.get("canDetect") else 0,
            ),
        )

    def process_activity_history(self, sid, uid, payload):
        """Stores a UserActivity event into UserActivityHistory and optionally upserts a Trip.

        UserActivity is a coarse-grained activity signal (IN_TRANSPORT, STATIONARY,
        etc.) emitted by the legacy activity API. It does not carry the full
        transport detail of DrivingInsights or Timeline events.

        When activityType is IN_TRANSPORT or tripType is set, a minimal Trip record
        is upserted using the sdk_source_event_id as the canonical transport ID
        (since UserActivity does not provide a Sentiance transport event ID). This
        ensures the trip is discoverable even when richer event types have not yet
        arrived.

        Args:
            sid:     sdk_source_event_id of the current SdkSourceEvent row.
            uid:     Sentiance user ID.
            payload: parsed UserActivity JSON dict.

        Returns:
            None
        """
        self.cursor.execute(
            "INSERT INTO UserActivityHistory (sdk_source_event_id, sentiance_user_id, activity_type, trip_type, stationary_latitude, stationary_longitude, payload_json, captured_at) VALUES (?, ?, ?, ?, ?, ?, ?, GETDATE())",
            (
                sid,
                uid,
                payload.get("activityType"),
                payload.get("tripType"),
                payload.get("stationaryLocation", {}).get("latitude"),
                payload.get("stationaryLocation", {}).get("longitude"),
                json.dumps(payload),
            ),
        )
        if payload.get("tripType") or payload.get("activityType") == "IN_TRANSPORT":
            transport = {
                "id": sid,
                "startTime": payload.get("startTime"),
                "transportMode": payload.get("tripType"),
            }
            self.upsert_trip(sid, uid, transport)

    def process_technical_event(self, sid, uid, payload):
        """Stores an internal SDK diagnostic event into TechnicalEventHistory.

        TechnicalEvents are emitted by the SDK for operational observability:
        configuration changes, detection-engine state transitions, background
        execution signals, etc. The full payload is preserved as JSON for
        forensic inspection without a fixed schema.

        Args:
            sid:     sdk_source_event_id of the current SdkSourceEvent row.
            uid:     Sentiance user ID.
            payload: parsed TechnicalEvent JSON dict containing at minimum
                     'type' and optionally 'message'.

        Returns:
            None
        """
        self.cursor.execute(
            "INSERT INTO TechnicalEventHistory (sdk_source_event_id, sentiance_user_id, technical_event_type, message, payload_json, captured_at) VALUES (?, ?, ?, ?, ?, GETDATE())",
            (
                sid,
                uid,
                payload.get("type"),
                payload.get("message"),
                json.dumps(payload),
            ),
        )

    def run(self, batch_size=500):
        """Fetches one batch of unprocessed records from SentianceEventos and processes them.

        Execution flow:
            1. Opens a database connection.
            2. Queries up to batch_size rows where is_processed = 0, ordered by id.
            3. For each row:
               a. Child DrivingInsights sub-event types (HarshEvents, PhoneEvents, etc.)
                  are skipped if their parent DrivingInsightsTrip does not yet exist,
                  leaving is_processed = 0 for a future retry.
               b. Inserts a SdkSourceEvent audit row (source_time, ref, hash).
               c. Routes to the appropriate process_* method based on tipo.
               d. Marks the original row as is_processed = 1 and commits.
               e. On any exception: rolls back, logs to SentianceEventos_Errors,
                  marks the row as is_processed = -1, reconnects if the connection
                  was lost, and continues with the next row.
            4. Returns False if the batch contained only orphan child events
               (all skipped), to prevent an infinite retry loop in the caller.

        Args:
            batch_size: maximum number of SentianceEventos rows to process per call.
                        Defaults to 500.

        Returns:
            True  if at least one record was successfully processed or failed
                  (i.e. the queue is making progress).
            False if no rows were found or every row in the batch was an orphan
                  child waiting for its parent (signals the caller to stop).
        """
        logger.info(f"Starting ETL Execution (Batch: {batch_size})")
        self.connect()
        logger.debug(f"Connected, about to execute query")
        try:
            types = (
                "'DrivingInsights'",
                "'DrivingInsightsHarshEvents'",
                "'DrivingInsightsPhoneEvents'",
                "'DrivingInsightsCallEvents'",
                "'DrivingInsightsSpeedingEvents'",
                "'DrivingInsightsWrongWayDrivingEvents'",
                "'UserContextUpdate'",
                "'requestUserContext'",
                "'TimelineEvents'",
                "'VehicleCrash'",
                "'SDKStatus'",
                "'UserMetadata'",
                "'TechnicalEvent'",
                "'UserActivity'",
                "'TimelineUpdate'",
            )
            query = f"SELECT TOP {batch_size} id, sentianceid, json, tipo FROM SentianceEventos WHERE is_processed = 0 AND tipo IN ({','.join(types)})"
            logger.debug(f"Query: {query}")
            self.cursor.execute(query)
            rows = self.cursor.fetchall()
            logger.debug(f"Fetched {len(rows)} rows")
            if not rows:
                return False

            # Define child event types that require a parent DrivingInsights record to exist
            child_event_types = (
                "'DrivingInsightsHarshEvents'",
                "'DrivingInsightsPhoneEvents'",
                "'DrivingInsightsCallEvents'",
                "'DrivingInsightsSpeedingEvents'",
                "'DrivingInsightsWrongWayDrivingEvents'",
            )

            processed_count = 0
            for r_id, uid, r_json, tipo in rows:
                try:
                    logger.debug(f"Processing {tipo} id={r_id} uid={uid}")
                    p = json.loads(r_json)

                    # For child events, verify parent DrivingInsights record exists BEFORE
                    # creating any downstream records (SdkSourceEvent, DrivingInsights*Event tables).
                    # This prevents orphaned child records when parent never arrives.
                    if tipo in (
                        "DrivingInsightsHarshEvents",
                        "DrivingInsightsPhoneEvents",
                        "DrivingInsightsCallEvents",
                        "DrivingInsightsSpeedingEvents",
                        "DrivingInsightsWrongWayDrivingEvents",
                    ):
                        transport_id = p.get("transportId")
                        if not transport_id:
                            logger.warning(
                                f"Child event {tipo} id={r_id} has no transportId, skipping"
                            )
                            self.cursor.execute(
                                "UPDATE SentianceEventos SET is_processed = -1 WHERE id = ?",
                                (r_id,),
                            )
                            self.conn.commit()
                            continue

                        # Check if parent DrivingInsightsTrip exists for this transport/user
                        parent_exists = self.cursor.execute(
                            "SELECT 1 FROM DrivingInsightsTrip WHERE canonical_transport_event_id = ? AND sentiance_user_id = ?",
                            (transport_id, uid),
                        ).fetchone()

                        if not parent_exists:
                            # Parent not found - skip this child, don't mark as processed.
                            # Child will remain with is_processed=0 and be retried on next ETL run.
                            # When parent arrives and is processed, the retry will succeed.
                            # If parent never arrives, periodic SentianceEventos purge will clean this up.
                            logger.warning(
                                f"Orphan child event detected: {tipo} id={r_id} transportId={transport_id} "
                                f"uid={uid} - no parent DrivingInsightsTrip found. Skipping (will retry)."
                            )
                            # Don't update is_processed - leave as 0 for retry
                            continue

                    st = self.format_ts(
                        p.get("transportEvent", {}).get("startTime")
                        or (
                            p[0].get("startTime") if isinstance(p, list) and p else None
                        )
                        or p.get("startTime")
                        or datetime.now().isoformat()
                    )
                    ref = (
                        p.get("transportEvent", {}).get("id")
                        or (p[0].get("id") if isinstance(p, list) and p else None)
                        or p.get("id")
                        or str(r_id)
                    )
                    self.cursor.execute(
                        "INSERT INTO SdkSourceEvent (sentiance_eventos_id, record_type, sentiance_user_id, source_time, source_event_ref, payload_hash, created_at) VALUES (?, ?, ?, ?, ?, ?, GETDATE())",
                        (r_id, tipo, uid, st, ref, self.get_hash(r_json)),
                    )
                    sid = self.cursor.execute("SELECT @@IDENTITY").fetchone()[0]
                    if tipo == "DrivingInsights":
                        self.process_driving_insights(sid, uid, p)
                    elif tipo == "DrivingInsightsHarshEvents":
                        self.process_driving_insights_harsh_events(sid, uid, p)
                    elif tipo == "DrivingInsightsPhoneEvents":
                        self.process_driving_insights_phone_events(sid, uid, p)
                    elif tipo == "DrivingInsightsCallEvents":
                        self.process_driving_insights_call_events(sid, uid, p)
                    elif tipo == "DrivingInsightsSpeedingEvents":
                        self.process_driving_insights_speeding_events(sid, uid, p)
                    elif tipo == "DrivingInsightsWrongWayDrivingEvents":
                        self.process_driving_insights_wrong_way_events(sid, uid, p)
                    elif tipo in ["UserContextUpdate", "requestUserContext"]:
                        self.process_user_context(
                            sid, uid, p, tipo == "requestUserContext"
                        )
                    elif tipo in ("TimelineEvents", "TimelineUpdate"):
                        self.process_timeline_events(sid, uid, p)
                    elif tipo == "UserMetadata":
                        self.process_metadata(uid, p)
                    elif tipo == "VehicleCrash":
                        self.process_crash_event(sid, uid, p)
                    elif tipo == "SDKStatus":
                        self.process_sdk_status(sid, uid, p)
                    elif tipo == "TechnicalEvent":
                        self.process_technical_event(sid, uid, p)
                    elif tipo == "UserActivity":
                        self.process_activity_history(sid, uid, p)
                    self.cursor.execute(
                        "UPDATE SentianceEventos SET is_processed = 1 WHERE id = ?",
                        (r_id,),
                    )
                    self.conn.commit()
                    processed_count += 1
                except Exception as e:
                    err_trace = traceback.format_exc()
                    try:
                        self.conn.rollback()
                    except Exception:
                        logger.warning(f"Rollback failed for id={r_id}, connection may be dead. Reconnecting.")
                        self.reconnect()
                    self.log_error_to_db(r_id, uid, tipo, r_json, err_trace)
                    try:
                        self.cursor.execute(
                            "UPDATE SentianceEventos SET is_processed = -1 WHERE id = ?",
                            (r_id,),
                        )
                        self.conn.commit()
                    except Exception:
                        logger.error(f"Could not mark id={r_id} as failed after connection loss; will be retried next run.")
            if processed_count == 0:
                logger.warning(
                    f"Batch fetched {len(rows)} records but processed 0 "
                    "(all were orphan children waiting for parent). Stopping to avoid infinite loop."
                )
                return False
            return True
        finally:
            self.close()


if __name__ == "__main__":
    import sys

    max_iterations = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    etl = SentianceETL()
    for i in range(max_iterations):
        if not etl.run(batch_size=1000):
            print(f"No more records to process after {i + 1} iterations")
            break
    else:
        print(f"Reached max iterations ({max_iterations})")
    print("ETL completed")
