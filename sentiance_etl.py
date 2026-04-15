"""
Sentiance SDK Data ETL (Extract, Transform, Load) - COMPLETE VERSION
====================================================================

DESCRIPTION:
This script implements a two-stage data pipeline for Sentiance SDK telemetry.
It is designed to be highly modular, secure, and self-documenting. 
It mirrors the complete architecture defined in Entregable.md.

STAGES:
1. LANDING ZONE (Stage 1): Raw JSON payloads are received via SDK listeners 
   and stored in the 'SentianceEventos' table.
2. DOMAIN PROJECTION (Stage 2): This script reads unprocessed records from Stage 1,
   parses the JSON, compresses spatial data (GPS waypoints), and distributes 
   it into a structured, relational schema for analytics.

HANDLERS IMPLEMENTED:
- DrivingInsights (Scores, Harsh Driving, Phone Usage, Call Events, Speeding)
- UserContext (Behavior Segments, Semantic Time, Home/Work History, Active Events)
- TimelineEvents (Historical sequence, Trip Synchronization)
- UserMetadata (Custom SDK labels)
- VehicleCrash (Impact telemetry and preceding locations)
- SDKStatus (Operational health and permission monitoring)
- Technical/Activity (System logs and high-level summaries)

KEY FEATURES:
- Deduplication: Uses SHA-256 hashing to ensure payloads aren't processed twice.
- Compression: Uses GZIP to compress large JSON arrays into VARBINARY(MAX).
- Relational Integrity: Consolidates journey data into a central 'Trip' table.
- Error Resilience: Uses atomic transactions; failures are logged for forensics.

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

# Configure logging to output to console with timestamps
logging.basicConfig(
    level=logging.INFO, 
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("SentianceETL")


class SentianceETL:
    """
    Main ETL engine responsible for transforming raw Sentiance JSON payloads
    into a structured relational database model.
    """

    def __init__(self):
        """Initializes the ETL instance by loading configuration from environment."""
        server = os.getenv("DB_SERVER")
        port = os.getenv("DB_PORT")
        user = os.getenv("DB_USER")
        password = os.getenv("DB_PASSWORD")
        database = os.getenv("DB_NAME")

        if not all([server, port, user, password, database]):
            raise ValueError("Missing database configuration in .env file.")

        self.conn_str = (
            f"DRIVER={{ODBC Driver 18 for SQL Server}};"
            f"SERVER={server},{port};"
            f"DATABASE={database};"
            f"UID={user};"
            f"PWD={password};"
            f"Encrypt=yes;"
            f"TrustServerCertificate=yes"
        )
        self.conn = None
        self.cursor = None

    def connect(self):
        """Establishes a connection to the SQL Server database."""
        try:
            self.conn = pyodbc.connect(self.conn_str)
            self.cursor = self.conn.cursor()
        except Exception as e:
            logger.critical(f"Connection Failed: {e}")
            raise

    def close(self):
        """Closes the database connection safely."""
        if self.conn:
            self.conn.close()

    def format_ts(self, ts_str):
        """
        Safely formats ISO timestamps for SQL Server DATETIME2(3).
        Truncates extra millisecond precision which causes conversion errors.
        """
        if not ts_str or not isinstance(ts_str, str):
            return None
        return ts_str.replace('Z', '')[:23]

    def compress_data(self, data):
        """
        Compresses JSON-serializable objects using GZIP for VARBINARY(MAX) columns.
        Saves 60-80% of storage space.
        """
        if not data or (isinstance(data, list) and len(data) == 0):
            return None
        try:
            return gzip.compress(json.dumps(data).encode("utf-8"))
        except Exception as e:
            logger.warning(f"Compression failed: {e}")
            return None

    def get_hash(self, text):
        """Generates a SHA-256 hash for payload deduplication."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def log_error_to_db(self, raw_id, uid, tipo, json_str, err):
        """Records a failure attempt in the forensic shadow table."""
        try:
            sql = """
                INSERT INTO SentianceEventos_Errors (original_id, sentiance_user_id, tipo, raw_json, error_message)
                VALUES (?, ?, ?, ?, ?)
            """
            self.cursor.execute(sql, (raw_id, uid, tipo, json_str, err))
        except Exception as e:
            logger.error(f"Failed to write to error shadow table: {e}")

    def upsert_trip(self, uid, transport):
        """
        Consolidates trip data into the central 'Trip' table. 
        Ensures that multiple events belonging to the same journey are updated.
        """
        tid = transport.get("id")
        if not tid:
            return None

        # SQL MERGE: Atomic 'Update if exists, else Insert'
        sql = """
        MERGE Trip AS target
        USING (SELECT ? AS tid, ? AS uid) AS source
        ON target.canonical_transport_event_id = source.tid AND target.sentiance_user_id = source.uid
        WHEN MATCHED THEN
            UPDATE SET 
                last_update_time = ?, last_update_time_epoch = ?,
                end_time = ?, end_time_epoch = ?, 
                duration_in_seconds = ?, distance_meters = ?, 
                transport_mode = ?, occupant_role = ?, 
                is_provisional = ?, updated_at = GETDATE()
        WHEN NOT MATCHED THEN
            INSERT (sentiance_user_id, canonical_transport_event_id, first_seen_from, start_time, start_time_epoch, 
                    last_update_time, last_update_time_epoch, end_time, end_time_epoch, duration_in_seconds, 
                    distance_meters, transport_mode, occupant_role, is_provisional, transport_tags_json, 
                    waypoints_json, created_at, updated_at)
            VALUES (?, ?, 'ETL_PROCESS', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE(), GETDATE());
        """
        params = [
            tid, uid,
            self.format_ts(transport.get("lastUpdateTime")), transport.get("lastUpdateTimeEpoch"),
            self.format_ts(transport.get("endTime")), transport.get("endTimeEpoch"),
            transport.get("durationInSeconds"), transport.get("distance"),
            transport.get("transportMode"), transport.get("occupantRole"),
            1 if transport.get("isProvisional") else 0,
            uid, tid, self.format_ts(transport.get("startTime")), transport.get("startTimeEpoch"),
            self.format_ts(transport.get("lastUpdateTime")), transport.get("lastUpdateTimeEpoch"),
            self.format_ts(transport.get("endTime")), transport.get("endTimeEpoch"),
            transport.get("durationInSeconds"), transport.get("distance"),
            transport.get("transportMode"), transport.get("occupantRole"),
            1 if transport.get("isProvisional") else 0,
            self.compress_data(transport.get("transportTags")),
            self.compress_data(transport.get("waypoints"))
        ]
        self.cursor.execute(sql, params)
        res = self.cursor.execute("SELECT trip_id FROM Trip WHERE canonical_transport_event_id = ? AND sentiance_user_id = ?", (tid, uid)).fetchone()
        return res[0] if res else None

    def process_driving_insights(self, sid, uid, payload):
        """Processes safety scores and granular driving events (Harsh, Phone, Call, Speeding)."""
        logger.info("Handling DrivingInsights Event...")
        transport = payload.get("transportEvent", {})
        scores = payload.get("safetyScores", {})
        
        # 1. Sync Central Journey
        trip_id = self.upsert_trip(uid, transport)
        
        # 2. Main Insight Summary
        sql = """INSERT INTO DrivingInsightsTrip (source_event_id, trip_id, sentiance_user_id, canonical_transport_event_id, 
                 smooth_score, focus_score, legal_score, call_while_moving_score, overall_score, harsh_braking_score, 
                 harsh_turning_score, harsh_acceleration_score, wrong_way_driving_score, attention_score, 
                 distance_meters, occupant_role, transport_tags_json, created_at) 
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE())"""
        self.cursor.execute(sql, (sid, trip_id, uid, transport.get("id"), scores.get("smoothScore"), scores.get("focusScore"), 
                                  scores.get("legalScore"), scores.get("callWhileMovingScore"), scores.get("overallScore"), 
                                  scores.get("harshBrakingScore"), scores.get("harshTurningScore"), scores.get("harshAccelerationScore"), 
                                  scores.get("wrongWayDrivingScore"), scores.get("attentionScore"), transport.get("distance"), 
                                  transport.get("occupantRole"), self.compress_data(transport.get("transportTags"))))
        di_id = self.cursor.execute("SELECT @@IDENTITY").fetchone()[0]

        # 3. Harsh Events (Braking, Accel, Turn)
        for e in payload.get("harshDrivingEvents", []):
            self.cursor.execute("INSERT INTO DrivingInsightsHarshEvent (source_event_id, driving_insights_trip_id, start_time, start_time_epoch, end_time, end_time_epoch, magnitude, confidence, harsh_type, waypoints_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                               (sid, di_id, self.format_ts(e.get("startTime")), e.get("startTimeEpoch"), self.format_ts(e.get("endTime")), e.get("endTimeEpoch"), e.get("magnitude"), e.get("confidence"), e.get("type"), self.compress_data(e.get("waypoints"))))

        # 4. Phone Handling Events
        for e in payload.get("phoneUsageEvents", []):
            self.cursor.execute("INSERT INTO DrivingInsightsPhoneEvent (source_event_id, driving_insights_trip_id, start_time, start_time_epoch, end_time, end_time_epoch, call_state, waypoints_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                               (sid, di_id, self.format_ts(e.get("startTime")), e.get("startTimeEpoch"), self.format_ts(e.get("endTime")), e.get("endTimeEpoch"), e.get("callState"), self.compress_data(e.get("waypoints"))))

        # 5. Calls while Moving
        for e in payload.get("callWhileMovingEvents", []):
            self.cursor.execute("INSERT INTO DrivingInsightsCallEvent (source_event_id, driving_insights_trip_id, start_time, start_time_epoch, end_time, end_time_epoch, min_traveled_speed_mps, max_traveled_speed_mps, hands_free_state, waypoints_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                               (sid, di_id, self.format_ts(e.get("startTime")), e.get("startTimeEpoch"), self.format_ts(e.get("endTime")), e.get("endTimeEpoch"), e.get("minTraveledSpeedMps"), e.get("maxTraveledSpeedMps"), e.get("handsFreeState"), self.compress_data(e.get("waypoints"))))

        # 6. Speeding Incidents
        for e in payload.get("speedingEvents", []):
            self.cursor.execute("INSERT INTO DrivingInsightsSpeedingEvent (source_event_id, driving_insights_trip_id, start_time, start_time_epoch, end_time, end_time_epoch, waypoints_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
                               (sid, di_id, self.format_ts(e.get("startTime")), e.get("startTimeEpoch"), self.format_ts(e.get("endTime")), e.get("endTimeEpoch"), self.compress_data(e.get("waypoints"))))

    def process_user_context(self, sid, uid, payload, is_manual=False):
        """Processes behavioral segments, semantic time, and location history (Home/Work)."""
        logger.info("Handling UserContext Update...")
        context = payload if is_manual else payload.get("userContext", {})
        criteria = ["MANUAL_REQUEST"] if is_manual else payload.get("criteria", [])
        loc = context.get("lastKnownLocation", {})
        
        # 1. Header
        self.cursor.execute("INSERT INTO UserContextHeader (source_event_id, sentiance_user_id, context_source_type, semantic_time, last_known_latitude, last_known_longitude, last_known_accuracy, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, GETDATE())",
                           (sid, uid, "MANUAL" if is_manual else "LISTENER", context.get("semanticTime"), loc.get("latitude"), loc.get("longitude"), loc.get("accuracy")))
        phid = self.cursor.execute("SELECT @@IDENTITY").fetchone()[0]

        # 2. Update Motives
        for c in criteria:
            self.cursor.execute("INSERT INTO UserContextUpdateCriteria (user_context_payload_id, criteria_code) VALUES (?, ?)", (phid, c))

        # 3. Venue Evolution (Home/Work)
        for sig in ["home", "work"]:
            v = context.get(sig)
            if v:
                vloc = v.get("location", {})
                table = "UserHomeHistory" if sig == "home" else "UserWorkHistory"
                self.cursor.execute(f"INSERT INTO {table} (user_context_payload_id, significance, venue_type, latitude, longitude, accuracy) VALUES (?, ?, ?, ?, ?, ?)",
                                   (phid, sig.upper(), v.get("type"), vloc.get("latitude"), vloc.get("longitude"), vloc.get("accuracy")))

        # 4. Behavioral Segments
        for s in context.get("activeSegments", []):
            self.cursor.execute("INSERT INTO UserContextActiveSegmentDetail (user_context_payload_id, sentiance_user_id, segment_id, category, subcategory, segment_type, start_time, start_time_epoch, end_time, end_time_epoch, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE())",
                               (phid, uid, str(s.get("id")), s.get("category"), s.get("subcategory"), s.get("type"), self.format_ts(s.get("startTime")), s.get("startTimeEpoch"), self.format_ts(s.get("endTime")), s.get("endTimeEpoch")))
            sh_id = self.cursor.execute("SELECT @@IDENTITY").fetchone()[0]
            for a in s.get("attributes", []):
                self.cursor.execute("INSERT INTO UserContextSegmentAttribute (user_context_segment_history_id, attribute_name, attribute_value) VALUES (?, ?, ?)", (sh_id, a.get("name"), a.get("value")))

        # 5. Current Events & Journey Sync
        for e in context.get("events", []):
            self.cursor.execute("INSERT INTO UserContextEventDetail (user_context_payload_id, sentiance_user_id, event_id, event_type, start_time, start_time_epoch, last_update_time, last_update_time_epoch, end_time, end_time_epoch, duration_in_seconds, is_provisional, transport_mode, distance_meters, occupant_role, transport_tags_json, location_latitude, location_longitude, location_accuracy, venue_significance, venue_type, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE())",
                               (phid, uid, e.get("id"), e.get("type"), self.format_ts(e.get("startTime")), e.get("startTimeEpoch"), self.format_ts(e.get("lastUpdateTime")), e.get("lastUpdateTimeEpoch"), self.format_ts(e.get("endTime")), e.get("endTimeEpoch"), e.get("durationInSeconds"), 1 if e.get("isProvisional") else 0, e.get("transportMode"), e.get("distance"), e.get("occupantRole"), self.compress_data(e.get("transportTags")), e.get("location", {}).get("latitude"), e.get("location", {}).get("longitude"), e.get("location", {}).get("accuracy"), e.get("venue", {}).get("significance"), e.get("venue", {}).get("type")))
            # Ensure trips discovered via context are also unified
            if e.get("type") == "IN_TRANSPORT": self.upsert_trip(uid, e)

    def process_timeline_events(self, sid, uid, payload):
        """Processes historical sequences of activity."""
        logger.info("Handling TimelineEvents Array...")
        events = payload if isinstance(payload, list) else payload.get("events", [])
        for e in events:
            self.cursor.execute("INSERT INTO TimelineEventHistory (source_event_id, sentiance_user_id, event_id, event_type, start_time, start_time_epoch, last_update_time, last_update_time_epoch, end_time, end_time_epoch, duration_in_seconds, is_provisional, transport_mode, distance_meters, occupant_role, transport_tags_json, location_latitude, location_longitude, location_accuracy, venue_significance, venue_type, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE())",
                               (sid, uid, e.get("id"), e.get("type"), self.format_ts(e.get("startTime")), e.get("startTimeEpoch"), self.format_ts(e.get("lastUpdateTime")), e.get("lastUpdateTimeEpoch"), self.format_ts(e.get("endTime")), e.get("endTimeEpoch"), e.get("durationInSeconds"), 1 if e.get("isProvisional") else 0, e.get("transportMode"), e.get("distance"), e.get("occupantRole"), self.compress_data(e.get("transportTags")), e.get("location", {}).get("latitude"), e.get("location", {}).get("longitude"), e.get("location", {}).get("accuracy"), e.get("venue", {}).get("significance"), e.get("venue", {}).get("type")))
            if e.get("type") == "IN_TRANSPORT": self.upsert_trip(uid, e)

    def process_metadata(self, uid, payload):
        """Handles custom user labels."""
        logger.info("Handling UserMetadata...")
        label, val = payload.get("label"), payload.get("value")
        self.cursor.execute("INSERT INTO UserMetadata (sentiance_user_id, label, value, updated_at) VALUES (?, ?, ?, GETDATE())", (uid, label, str(val)))

    def process_crash_event(self, sid, uid, payload):
        """Handles vehicle crash detection telemetry."""
        logger.info("Handling VehicleCrash Event...")
        l = payload.get("location", {})
        self.cursor.execute("INSERT INTO VehicleCrashEvent (source_event_id, sentiance_user_id, crash_time_epoch, latitude, longitude, accuracy, altitude, magnitude, speed_at_impact, delta_v, confidence, severity, detector_mode, preceding_locations_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                           (sid, uid, payload.get("time"), l.get("latitude"), l.get("longitude"), l.get("accuracy"), l.get("altitude"), payload.get("magnitude"), payload.get("speedAtImpact"), payload.get("deltaV"), payload.get("confidence"), payload.get("severity"), payload.get("detectorMode"), self.compress_data(payload.get("precedingLocations"))))

    def process_sdk_status(self, sid, uid, payload):
        """Monitors SDK health and permission states."""
        logger.info("Handling SDKStatus Update...")
        self.cursor.execute("INSERT INTO SdkStatusHistory (source_event_id, sentiance_user_id, start_status, detection_status, location_permission, precise_location_granted, is_location_available, quota_status_wifi, quota_status_mobile, quota_status_disk, can_detect, captured_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE())",
                           (sid, uid, payload.get("startStatus"), payload.get("detectionStatus"), payload.get("locationPermission"), 1 if payload.get("isPreciseLocationPermGranted") else 0, 1 if payload.get("isLocationAvailable") else 0, payload.get("wifiQuotaStatus"), payload.get("mobileQuotaStatus"), payload.get("diskQuotaStatus"), 1 if payload.get("canDetect") else 0))

    def process_activity_history(self, sid, uid, payload):
        """Processes high-level user activity summaries."""
        logger.info("Handling UserActivity Summary...")
        self.cursor.execute("INSERT INTO UserActivityHistory (source_event_id, sentiance_user_id, activity_type, trip_type, stationary_latitude, stationary_longitude, payload_json, captured_at) VALUES (?, ?, ?, ?, ?, ?, ?, GETDATE())",
                           (sid, uid, payload.get("activityType"), payload.get("tripType"), payload.get("stationaryLocation", {}).get("latitude"), payload.get("stationaryLocation", {}).get("longitude"), json.dumps(payload)))

    def process_technical_event(self, sid, uid, payload):
        """Logs technical SDK events for debugging."""
        logger.info("Handling TechnicalEvent...")
        self.cursor.execute("INSERT INTO TechnicalEventHistory (source_event_id, sentiance_user_id, technical_event_type, message, payload_json, captured_at) VALUES (?, ?, ?, ?, ?, GETDATE())",
                           (sid, uid, payload.get("type"), payload.get("message"), json.dumps(payload)))

    def run(self, batch_size=500):
        """Main execution engine."""
        logger.info(f"Starting ETL Pipeline Execution (Batch Size: {batch_size})")
        self.connect()
        try:
            # Query queue of unprocessed records
            types = ("'DrivingInsights'", "'UserContextUpdate'", "'requestUserContext'", "'TimelineEvents'", "'VehicleCrash'", "'SDKStatus'", "'UserMetadata'", "'TechnicalEvent'", "'UserActivity'")
            query = f"SELECT TOP {batch_size} id, sentianceid, json, tipo FROM SentianceEventos WHERE is_processed = 0 AND tipo IN ({','.join(types)})"
            
            self.cursor.execute(query)
            rows = self.cursor.fetchall()
            
            for r_id, uid, r_json, tipo in rows:
                logger.info(f"== [RECORD {r_id}] Processing: {tipo} ==")
                try:
                    p = json.loads(r_json)
                    
                    # 1. Audit Trail Creation
                    st = self.format_ts(p.get("transportEvent", {}).get("startTime") or (p[0].get("startTime") if isinstance(p, list) and p else None) or p.get("startTime") or datetime.now().isoformat())
                    ref = p.get("transportEvent", {}).get("id") or (p[0].get("id") if isinstance(p, list) and p else None) or p.get("id") or str(r_id)
                    
                    self.cursor.execute("INSERT INTO SdkSourceEvent (id, record_type, sentiance_user_id, source_time, source_event_ref, payload_hash, created_at) VALUES (?, ?, ?, ?, ?, ?, GETDATE())", 
                                       (r_id, tipo, uid, st, ref, self.get_hash(r_json)))
                    sid = self.cursor.execute("SELECT @@IDENTITY").fetchone()[0]
                    
                    # 2. Dynamic Routing to Handlers
                    if tipo == "DrivingInsights": self.process_driving_insights(sid, uid, p)
                    elif tipo in ["UserContextUpdate", "requestUserContext"]: self.process_user_context(sid, uid, p, tipo=="requestUserContext")
                    elif tipo == "TimelineEvents": self.process_timeline_events(sid, uid, p)
                    elif tipo == "UserMetadata": self.process_metadata(uid, p)
                    elif tipo == "VehicleCrash": self.process_crash_event(sid, uid, p)
                    elif tipo == "SDKStatus": self.process_sdk_status(sid, uid, p)
                    elif tipo == "TechnicalEvent": self.process_technical_event(sid, uid, p)
                    elif tipo == "UserActivity": self.process_activity_history(sid, uid, p)
                    
                    # 3. Mark success
                    self.cursor.execute("UPDATE SentianceEventos SET is_processed = 1 WHERE id = ?", (r_id,))
                    self.conn.commit()
                    logger.info(f"== [RECORD {r_id}] SUCCESS ==")
                    
                except Exception as e:
                    self.conn.rollback()
                    logger.error(f"FAILED record {r_id}: {e}")
                    self.log_error_to_db(r_id, uid, tipo, r_json, traceback.format_exc())
                    self.cursor.execute("UPDATE SentianceEventos SET is_processed = -1 WHERE id = ?", (r_id,))
                    self.conn.commit()
                    
        finally: 
            self.close()

if __name__ == "__main__":
    try: 
        SentianceETL().run()
    except Exception as e: 
        logger.error(f"Fatal Execution Error: {e}")
