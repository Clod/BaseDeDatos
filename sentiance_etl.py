"""
Sentiance SDK Data ETL (Extract, Transform, Load)
===============================================

DESCRIPTION:
This script implements a two-stage data pipeline for Sentiance SDK telemetry.
It is designed to be highly modular, secure, and self-documenting.

STAGES:
1. LANDING ZONE (Stage 1): Raw JSON payloads are received via SDK listeners 
   and stored in the 'SentianceEventos' table.
2. DOMAIN PROJECTION (Stage 2): This script reads unprocessed records from Stage 1,
   parses the JSON, compresses spatial data (GPS waypoints), and distributes 
   it into a structured, relational schema for analytics.

KEY FEATURES:
- Deduplication: Uses SHA-256 hashing to ensure payloads aren't processed twice.
- Compression: Uses GZIP to compress large JSON arrays (waypoints) into VARBINARY(MAX).
- Relational Integrity: Consolidates trip data into a central 'Trip' table.
- Error Resilience: Uses atomic transactions; failed records are logged for forensics.

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

# Configure logging
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
            raise ValueError("Missing database configuration in environment variables.")

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
        # Sentiance format: 2026-04-15T13:28:45.123456Z
        # SQL Server DATETIME2(3) target: 2026-04-15T13:28:45.123
        return ts_str.replace('Z', '')[:23]

    def compress_data(self, data):
        """Compresses JSON-serializable objects using GZIP."""
        if data is None or (isinstance(data, list) and len(data) == 0):
            return None
        try:
            return gzip.compress(json.dumps(data).encode("utf-8"))
        except:
            return None

    def get_hash(self, text):
        """Generates a SHA-256 hash for deduplication."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def log_error_to_db(self, original_id, sentiance_id, tipo, raw_json, error_msg):
        """Records a failure attempt in the forensic shadow table."""
        try:
            sql = """
                INSERT INTO SentianceEventos_Errors (original_id, sentiance_user_id, tipo, raw_json, error_message)
                VALUES (?, ?, ?, ?, ?)
            """
            self.cursor.execute(sql, (original_id, sentiance_id, tipo, raw_json, error_msg))
        except Exception as e:
            logger.error(f"Failed to write to error shadow table: {e}")

    def upsert_trip(self, sentiance_user_id, transport_event):
        """Consolidates trip data into the central 'Trip' table."""
        canonical_id = transport_event.get("id")
        if not canonical_id:
            return None

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
            INSERT (sentiance_user_id, canonical_transport_event_id, first_seen_from, 
                    start_time, start_time_epoch, last_update_time, last_update_time_epoch,
                    end_time, end_time_epoch, duration_in_seconds, distance_meters, 
                    transport_mode, occupant_role, is_provisional, 
                    transport_tags_json, waypoints_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE(), GETDATE());
        """

        params = [
            canonical_id, sentiance_user_id,
            self.format_ts(transport_event.get("lastUpdateTime")), transport_event.get("lastUpdateTimeEpoch"),
            self.format_ts(transport_event.get("endTime")), transport_event.get("endTimeEpoch"),
            transport_event.get("durationInSeconds"), transport_event.get("distance"),
            transport_event.get("transportMode"), transport_event.get("occupantRole"),
            1 if transport_event.get("isProvisional") else 0,
            sentiance_user_id, canonical_id, "ETL_PROCESS",
            self.format_ts(transport_event.get("startTime")), transport_event.get("startTimeEpoch"),
            self.format_ts(transport_event.get("lastUpdateTime")), transport_event.get("lastUpdateTimeEpoch"),
            self.format_ts(transport_event.get("endTime")), transport_event.get("endTimeEpoch"),
            transport_event.get("durationInSeconds"), transport_event.get("distance"),
            transport_event.get("transportMode"), transport_event.get("occupantRole"),
            1 if transport_event.get("isProvisional") else 0,
            self.compress_data(transport_event.get("transportTags")),
            self.compress_data(transport_event.get("waypoints")),
        ]
        self.cursor.execute(sql, params)
        
        self.cursor.execute("SELECT trip_id FROM Trip WHERE canonical_transport_event_id = ? AND sentiance_user_id = ?", (canonical_id, sentiance_user_id))
        res = self.cursor.fetchone()
        return res[0] if res else None

    def process_driving_insights(self, source_event_id, sentiance_user_id, payload):
        """Processes scores and harsh events."""
        transport = payload.get("transportEvent", {})
        scores = payload.get("safetyScores", {})
        trip_id = self.upsert_trip(sentiance_user_id, transport)

        sql = """
        INSERT INTO DrivingInsightsTrip (
            source_event_id, trip_id, sentiance_user_id, canonical_transport_event_id,
            smooth_score, focus_score, legal_score, call_while_moving_score, overall_score,
            harsh_braking_score, harsh_turning_score, harsh_acceleration_score, 
            wrong_way_driving_score, attention_score, distance_meters, occupant_role, 
            transport_tags_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE())
        """
        params = [
            source_event_id, trip_id, sentiance_user_id, transport.get("id"),
            scores.get("smoothScore"), scores.get("focusScore"), scores.get("legalScore"),
            scores.get("callWhileMovingScore"), scores.get("overallScore"),
            scores.get("harshBrakingScore"), scores.get("harshTurningScore"),
            scores.get("harshAccelerationScore"), scores.get("wrongWayDrivingScore"),
            scores.get("attentionScore"), transport.get("distance"), transport.get("occupantRole"),
            self.compress_data(transport.get("transportTags")),
        ]
        self.cursor.execute(sql, params)
        di_trip_id = self.cursor.execute("SELECT @@IDENTITY").fetchone()[0]

        for event in payload.get("harshDrivingEvents", []):
            self.cursor.execute("""
                INSERT INTO DrivingInsightsHarshEvent (
                    source_event_id, driving_insights_trip_id, start_time, start_time_epoch,
                    end_time, end_time_epoch, magnitude, confidence, harsh_type, waypoints_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (source_event_id, di_trip_id, self.format_ts(event.get("startTime")), event.get("startTimeEpoch"),
                  self.format_ts(event.get("endTime")), event.get("endTimeEpoch"), event.get("magnitude"),
                  event.get("confidence"), event.get("type"), self.compress_data(event.get("waypoints"))))

    def process_user_context(self, source_event_id, sentiance_user_id, payload, is_manual=False):
        """Processes behavioral segments and venue history."""
        if is_manual:
            context = payload
            criteria = ["MANUAL_REQUEST"]
        else:
            context = payload.get("userContext", {})
            criteria = payload.get("criteria", [])

        loc = context.get("lastKnownLocation", {})
        self.cursor.execute("""
            INSERT INTO UserContextHeader (
                source_event_id, sentiance_user_id, context_source_type, semantic_time,
                last_known_latitude, last_known_longitude, last_known_accuracy, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, GETDATE())
        """, (source_event_id, sentiance_user_id, "MANUAL" if is_manual else "LISTENER",
              context.get("semanticTime"), loc.get("latitude"), loc.get("longitude"), loc.get("accuracy")))
        payload_id = self.cursor.execute("SELECT @@IDENTITY").fetchone()[0]

        for code in criteria:
            self.cursor.execute("INSERT INTO UserContextUpdateCriteria (user_context_payload_id, criteria_code) VALUES (?, ?)", (payload_id, code))

        for sig in ["home", "work"]:
            venue = context.get(sig)
            if venue:
                v_loc = venue.get("location", {})
                table = "UserHomeHistory" if sig == "home" else "UserWorkHistory"
                self.cursor.execute(f"INSERT INTO {table} (user_context_payload_id, significance, venue_type, latitude, longitude, accuracy) VALUES (?, ?, ?, ?, ?, ?)",
                                   (payload_id, sig.upper(), venue.get("type"), v_loc.get("latitude"), v_loc.get("longitude"), v_loc.get("accuracy")))

        for segment in context.get("activeSegments", []):
            self.cursor.execute("""
                INSERT INTO UserContextActiveSegmentDetail (
                    user_context_payload_id, sentiance_user_id, segment_id, category, subcategory, segment_type,
                    start_time, start_time_epoch, end_time, end_time_epoch, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE())
            """, (payload_id, sentiance_user_id, str(segment.get("id")), segment.get("category"), 
                  segment.get("subcategory"), segment.get("type"),
                  self.format_ts(segment.get("startTime")), segment.get("startTimeEpoch"),
                  self.format_ts(segment.get("endTime")), segment.get("endTimeEpoch")))
            
            seg_history_id = self.cursor.execute("SELECT @@IDENTITY").fetchone()[0]
            
            for attr in segment.get("attributes", []):
                self.cursor.execute("INSERT INTO UserContextSegmentAttribute (user_context_segment_history_id, attribute_name, attribute_value) VALUES (?, ?, ?)", 
                                   (seg_history_id, attr.get("name"), attr.get("value")))

        for event in context.get("events", []):
            self.cursor.execute("""
                INSERT INTO UserContextEventDetail (
                    user_context_payload_id, sentiance_user_id, event_id, event_type,
                    start_time, start_time_epoch, last_update_time, last_update_time_epoch,
                    end_time, end_time_epoch, duration_in_seconds, is_provisional,
                    transport_mode, distance_meters, occupant_role, transport_tags_json,
                    location_latitude, location_longitude, location_accuracy,
                    venue_significance, venue_type, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE())
            """, (payload_id, sentiance_user_id, event.get("id"), event.get("type"),
                  self.format_ts(event.get("startTime")), event.get("startTimeEpoch"),
                  self.format_ts(event.get("lastUpdateTime")), event.get("lastUpdateTimeEpoch"),
                  self.format_ts(event.get("endTime")), event.get("endTimeEpoch"),
                  event.get("durationInSeconds"), 1 if event.get("isProvisional") else 0,
                  event.get("transportMode"), event.get("distance"), event.get("occupantRole"),
                  self.compress_data(event.get("transportTags")),
                  event.get("location", {}).get("latitude"), event.get("location", {}).get("longitude"), 
                  event.get("location", {}).get("accuracy"), event.get("venue", {}).get("significance"), 
                  event.get("venue", {}).get("type")))

    def process_timeline_events(self, source_event_id, sentiance_user_id, payload):
        """Processes historical timeline updates."""
        events = payload if isinstance(payload, list) else payload.get("events", [])
        for event in events:
            self.cursor.execute("""
                INSERT INTO TimelineEventHistory (
                    source_event_id, sentiance_user_id, event_id, event_type,
                    start_time, start_time_epoch, last_update_time, last_update_time_epoch,
                    end_time, end_time_epoch, duration_in_seconds, is_provisional,
                    transport_mode, distance_meters, occupant_role, transport_tags_json,
                    location_latitude, location_longitude, location_accuracy,
                    venue_significance, venue_type, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE())
            """, (source_event_id, sentiance_user_id, event.get("id"), event.get("type"),
                  self.format_ts(event.get("startTime")), event.get("startTimeEpoch"),
                  self.format_ts(event.get("lastUpdateTime")), event.get("lastUpdateTimeEpoch"),
                  self.format_ts(event.get("endTime")), event.get("endTimeEpoch"),
                  event.get("durationInSeconds"), 1 if event.get("isProvisional") else 0,
                  event.get("transportMode"), event.get("distance"), event.get("occupantRole"),
                  self.compress_data(event.get("transportTags")),
                  event.get("location", {}).get("latitude"), event.get("location", {}).get("longitude"), 
                  event.get("location", {}).get("accuracy"), event.get("venue", {}).get("significance"), 
                  event.get("venue", {}).get("type")))
            
            if event.get("type") == "IN_TRANSPORT":
                self.upsert_trip(sentiance_user_id, event)

    def process_crash_event(self, source_event_id, sentiance_user_id, payload):
        """Processes impact detection telemetry."""
        loc = payload.get("location", {})
        self.cursor.execute("""
            INSERT INTO VehicleCrashEvent (
                source_event_id, sentiance_user_id, crash_time_epoch,
                latitude, longitude, accuracy, altitude,
                magnitude, speed_at_impact, delta_v, confidence,
                severity, detector_mode, preceding_locations_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (source_event_id, sentiance_user_id, payload.get("time"),
              loc.get("latitude"), loc.get("longitude"), loc.get("accuracy"), loc.get("altitude"),
              payload.get("magnitude"), payload.get("speedAtImpact"), payload.get("deltaV"),
              payload.get("confidence"), payload.get("severity"), payload.get("detectorMode"),
              self.compress_data(payload.get("precedingLocations"))))

    def process_sdk_status(self, source_event_id, sentiance_user_id, payload):
        """Processes operational health monitoring."""
        self.cursor.execute("""
            INSERT INTO SdkStatusHistory (
                source_event_id, sentiance_user_id, start_status, detection_status,
                location_permission, precise_location_granted, is_location_available,
                quota_status_wifi, quota_status_mobile, quota_status_disk,
                can_detect, captured_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE())
        """, (source_event_id, sentiance_user_id, payload.get("startStatus"), payload.get("detectionStatus"),
              payload.get("locationPermission"), 1 if payload.get("isPreciseLocationPermGranted") else 0,
              1 if payload.get("isLocationAvailable") else 0, payload.get("wifiQuotaStatus"), 
              payload.get("mobileQuotaStatus"), payload.get("diskQuotaStatus"), 1 if payload.get("canDetect") else 0))

    def run(self, batch_size=50):
        """Main execution loop."""
        logger.info(f"Starting Batch Execution ({batch_size} records)...")
        self.connect()
        try:
            implemented_types = ("'DrivingInsights'", "'UserContextUpdate'", "'requestUserContext'", "'TimelineEvents'", "'VehicleCrash'", "'SDKStatus'")
            query = f"SELECT TOP {batch_size} id, sentianceid, json, tipo FROM SentianceEventos WHERE is_processed = 0 AND tipo IN ({','.join(implemented_types)})"
            self.cursor.execute(query)
            rows = self.cursor.fetchall()
            
            for row in rows:
                raw_id, sentiance_id, raw_json, tipo = row
                logger.info(f"== [RECORD {raw_id}] Type: {tipo} ==")
                try:
                    payload = json.loads(raw_json)
                    source_time_str = (payload.get("transportEvent", {}).get("startTime") or (payload[0].get("startTime") if isinstance(payload, list) and payload else None) or payload.get("startTime") or datetime.now().isoformat())
                    source_ref = (payload.get("transportEvent", {}).get("id") or (payload[0].get("id") if isinstance(payload, list) and payload else None) or payload.get("id") or str(raw_id))
                    
                    self.cursor.execute("INSERT INTO SdkSourceEvent (id, record_type, sentiance_user_id, source_time, source_event_ref, payload_hash, created_at) VALUES (?, ?, ?, ?, ?, ?, GETDATE())",
                                       (raw_id, tipo, sentiance_id, self.format_ts(source_time_str), source_ref, self.get_hash(raw_json)))
                    source_event_id = self.cursor.execute("SELECT @@IDENTITY").fetchone()[0]
                    
                    if tipo == "DrivingInsights": self.process_driving_insights(source_event_id, sentiance_id, payload)
                    elif tipo in ["UserContextUpdate", "requestUserContext"]: self.process_user_context(source_event_id, sentiance_id, payload, (tipo == "requestUserContext"))
                    elif tipo == "TimelineEvents": self.process_timeline_events(source_event_id, sentiance_id, payload)
                    elif tipo == "VehicleCrash": self.process_crash_event(source_event_id, sentiance_id, payload)
                    elif tipo == "SDKStatus": self.process_sdk_status(source_event_id, sentiance_id, payload)
                    
                    self.cursor.execute("UPDATE SentianceEventos SET is_processed = 1 WHERE id = ?", (raw_id,))
                    self.conn.commit()
                    logger.info(f"== [RECORD {raw_id}] DONE ==")
                except Exception as e:
                    self.conn.rollback()
                    logger.error(f"FAILED {raw_id}: {e}")
                    self.log_error_to_db(raw_id, sentiance_id, tipo, raw_json, traceback.format_exc())
                    self.cursor.execute("UPDATE SentianceEventos SET is_processed = -1 WHERE id = ?", (raw_id,))
                    self.conn.commit()
        finally:
            self.close()

if __name__ == "__main__":
    try:
        SentianceETL().run(batch_size=50)
    except Exception as e:
        logger.error(f"Fatal: {e}")
