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
    Main ETL engine responsible for transforming raw Sentiance JSON payloads
    into a structured relational database model.
    """

    def __init__(self):
        """Initializes the ETL instance by loading configuration from environment."""
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
        """Establishes a connection to the SQL Server database."""
        self.conn = pyodbc.connect(self.conn_str)
        self.cursor = self.conn.cursor()

    def reconnect(self):
        """Drops the current connection and opens a fresh one."""
        try:
            if self.conn:
                self.conn.close()
        except Exception:
            pass
        self.conn = pyodbc.connect(self.conn_str)
        self.cursor = self.conn.cursor()

    def close(self):
        """Closes the database connection safely."""
        if self.conn:
            self.conn.close()

    def format_ts(self, ts_str):
        """Safely formats ISO timestamps for SQL Server DATETIME2(3)."""
        if not ts_str:
            return None
        return ts_str.replace("Z", "").replace("T", " ")[:23]

    def compress_data(self, data):
        """GZIP compression for VARBINARY(MAX) columns."""
        if not data:
            return None
        return gzip.compress(json.dumps(data).encode("utf-8"))

    def get_hash(self, text):
        """Generates SHA-256 hash for deduplication."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def log_error_to_db(self, raw_id, uid, tipo, json_str, err):
        """Records a failure attempt in the forensic shadow table."""
        try:
            self.cursor.execute(
                "INSERT INTO SentianceEventos_Errors (original_id, sentiance_user_id, tipo, raw_json, error_message) VALUES (?, ?, ?, ?, ?)",
                (raw_id, uid, tipo, json_str, err),
            )
        except:
            pass

    def upsert_trip(self, uid, transport):
        """Consolidates trip data into the central 'Trip' table."""
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
                       is_provisional = ?, updated_at = GETDATE()
        WHEN NOT MATCHED THEN
            INSERT (sentiance_user_id, canonical_transport_event_id, first_seen_from, start_time, start_time_epoch, 
                    last_update_time, last_update_time_epoch, end_time, end_time_epoch, duration_in_seconds, 
                    distance_meters, transport_mode, occupant_role, is_provisional, transport_tags_json, 
                    waypoints_json, created_at, updated_at)
            VALUES (?, ?, 'ETL_PROCESS', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE(), GETDATE());
        """
        params = [
            tid,
            uid,
            self.format_ts(transport.get("lastUpdateTime")),
            transport.get("lastUpdateTimeEpoch"),
            self.format_ts(transport.get("endTime")),
            transport.get("endTimeEpoch"),
            transport.get("durationInSeconds"),
            transport.get("distance"),
            transport.get("transportMode"),
            transport.get("occupantRole"),
            1 if transport.get("isProvisional") else 0,
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
        ]
        self.cursor.execute(sql, params)
        res = self.cursor.execute(
            "SELECT trip_id FROM Trip WHERE canonical_transport_event_id = ? AND sentiance_user_id = ?",
            (tid, uid),
        ).fetchone()
        return res[0] if res else None

    def process_driving_insights(self, sid, uid, payload):
        """Processes safety scores and granular driving incidents."""
        transport = payload.get("transportEvent", {})
        scores = payload.get("safetyScores", {})
        trip_id = self.upsert_trip(uid, transport)

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
        di_id = self.cursor.execute("SELECT @@IDENTITY").fetchone()[0]

        for e in payload.get("harshDrivingEvents", []):
            self.cursor.execute(
                "INSERT INTO DrivingInsightsHarshEvent (sdk_source_event_id, driving_insights_trip_id, start_time, start_time_epoch, end_time, end_time_epoch, magnitude, confidence, harsh_type, waypoints_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    sid,
                    di_id,
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

        for e in payload.get("phoneUsageEvents", []):
            self.cursor.execute(
                "INSERT INTO DrivingInsightsPhoneEvent (sdk_source_event_id, driving_insights_trip_id, start_time, start_time_epoch, end_time, end_time_epoch, call_state, waypoints_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    sid,
                    di_id,
                    self.format_ts(e.get("startTime")),
                    e.get("startTimeEpoch"),
                    self.format_ts(e.get("endTime")),
                    e.get("endTimeEpoch"),
                    e.get("callState"),
                    self.compress_data(e.get("waypoints")),
                ),
            )

        for e in payload.get("callWhileMovingEvents", []):
            self.cursor.execute(
                "INSERT INTO DrivingInsightsCallEvent (sdk_source_event_id, driving_insights_trip_id, start_time, start_time_epoch, end_time, end_time_epoch, min_traveled_speed_mps, max_traveled_speed_mps, hands_free_state, waypoints_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    sid,
                    di_id,
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

        for e in payload.get("speedingEvents", []):
            self.cursor.execute(
                "INSERT INTO DrivingInsightsSpeedingEvent (sdk_source_event_id, driving_insights_trip_id, start_time, start_time_epoch, end_time, end_time_epoch, waypoints_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    sid,
                    di_id,
                    self.format_ts(e.get("startTime")),
                    e.get("startTimeEpoch"),
                    self.format_ts(e.get("endTime")),
                    e.get("endTimeEpoch"),
                    self.compress_data(e.get("waypoints")),
                ),
            )

    def process_driving_insights_harsh_events(self, sid, uid, payload):
        """Processes standalone harsh driving events fetched via getHarshDrivingEvents."""
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
        """Processes standalone phone usage events fetched via getPhoneUsageEvents."""
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
        """Processes standalone call events fetched via getCallEvents."""
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
        """Processes standalone speeding events fetched via getSpeedingEvents."""
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
        """Processes standalone wrong way driving events fetched via getWrongWayDrivingEvents."""
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
        """Processes behavioral segments, semantic time, and location history."""
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
                self.upsert_trip(uid, e)

    def process_timeline_events(self, sid, uid, payload):
        """Processes historical sequences of activity."""
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
                self.upsert_trip(uid, e)

    def process_metadata(self, uid, payload):
        """Handles custom user metadata labels."""
        label, val = payload.get("label"), payload.get("value")
        self.cursor.execute(
            "INSERT INTO UserMetadata (sentiance_user_id, label, value, updated_at) VALUES (?, ?, ?, GETDATE())",
            (uid, label, str(val)),
        )

    def process_crash_event(self, sid, uid, payload):
        """Handles vehicle crash detection telemetry."""
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
        """Monitors SDK health and permission states."""
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
        """Processes high-level activity summaries."""
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
            self.upsert_trip(uid, transport)

    def process_technical_event(self, sid, uid, payload):
        """Logs technical SDK events for debugging."""
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
        """
        Main execution loop. Fetches unprocessed records and routes to handlers.
        Returns True if data was processed, False otherwise.
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
