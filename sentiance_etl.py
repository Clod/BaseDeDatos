"""
Sentiance SDK Data ETL (Extract, Transform, Load) - COMPLETE VERSION
====================================================================

DESCRIPTION:
This script implements a two-stage data pipeline for Sentiance SDK telemetry.
It mirrors the complete architecture defined in Entregable.md.

STAGES:
1. LANDING ZONE (Stage 1): Raw JSON payloads from SentianceEventos.
2. DOMAIN PROJECTION (Stage 2): Distributed relational model for analytics.

HANDLERS:
- DrivingInsights (Scores, Harsh, Phone, Call, Speeding, WrongWay)
- UserContext (Segments, Semantic Time, Home/Work History, Context Events)
- TimelineEvents (Historical sequence, Trip Synchronization)
- UserMetadata (Custom SDK labels)
- VehicleCrash (Impact telemetry)
- SDKStatus (Operational health)
- Technical/Activity (System logs and high-level summaries)

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

# Load database credentials
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO, 
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("SentianceETL")


class SentianceETL:
    def __init__(self):
        server, port, user, pwd, db = os.getenv("DB_SERVER"), os.getenv("DB_PORT"), os.getenv("DB_USER"), os.getenv("DB_PASSWORD"), os.getenv("DB_NAME")
        if not all([server, port, user, pwd, db]):
            raise ValueError("Missing database configuration in .env")
        self.conn_str = f"DRIVER={{ODBC Driver 18 for SQL Server}};SERVER={server},{port};DATABASE={db};UID={user};PWD={pwd};Encrypt=yes;TrustServerCertificate=yes"
        self.conn, self.cursor = None, None

    def connect(self):
        self.conn = pyodbc.connect(self.conn_str)
        self.cursor = self.conn.cursor()

    def close(self):
        if self.conn: self.conn.close()

    def format_ts(self, ts_str):
        """Truncate to 23 chars for DATETIME2(3) compatibility."""
        return ts_str.replace('Z', '')[:23] if ts_str else None

    def compress_data(self, data):
        """GZIP compression for VARBINARY(MAX)."""
        if not data: return None
        return gzip.compress(json.dumps(data).encode("utf-8"))

    def get_hash(self, text):
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def log_error_to_db(self, raw_id, uid, tipo, json_str, err):
        try:
            self.cursor.execute("INSERT INTO SentianceEventos_Errors (original_id, sentiance_user_id, tipo, raw_json, error_message) VALUES (?, ?, ?, ?, ?)",
                               (raw_id, uid, tipo, json_str, err))
        except: pass

    def upsert_trip(self, uid, transport):
        tid = transport.get("id")
        if not tid: return None
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
        params = [tid, uid, self.format_ts(transport.get("lastUpdateTime")), transport.get("lastUpdateTimeEpoch"),
                  self.format_ts(transport.get("endTime")), transport.get("endTimeEpoch"), transport.get("durationInSeconds"),
                  transport.get("distance"), transport.get("transportMode"), transport.get("occupantRole"), 1 if transport.get("isProvisional") else 0,
                  uid, tid, self.format_ts(transport.get("startTime")), transport.get("startTimeEpoch"),
                  self.format_ts(transport.get("lastUpdateTime")), transport.get("lastUpdateTimeEpoch"),
                  self.format_ts(transport.get("endTime")), transport.get("endTimeEpoch"), transport.get("durationInSeconds"),
                  transport.get("distance"), transport.get("transportMode"), transport.get("occupantRole"),
                  1 if transport.get("isProvisional") else 0, self.compress_data(transport.get("transportTags")),
                  self.compress_data(transport.get("waypoints"))]
        self.cursor.execute(sql, params)
        return self.cursor.execute("SELECT trip_id FROM Trip WHERE canonical_transport_event_id = ?", (tid,)).fetchone()[0]

    def process_driving_insights(self, sid, uid, payload):
        transport = payload.get("transportEvent", {})
        scores = payload.get("safetyScores", {})
        trip_id = self.upsert_trip(uid, transport)
        
        # 1. Main Insight Entry
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

        # 2. Harsh Events
        for e in payload.get("harshDrivingEvents", []):
            self.cursor.execute("INSERT INTO DrivingInsightsHarshEvent (source_event_id, driving_insights_trip_id, start_time, start_time_epoch, end_time, end_time_epoch, magnitude, confidence, harsh_type, waypoints_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                               (sid, di_id, self.format_ts(e.get("startTime")), e.get("startTimeEpoch"), self.format_ts(e.get("endTime")), e.get("endTimeEpoch"), e.get("magnitude"), e.get("confidence"), e.get("type"), self.compress_data(e.get("waypoints"))))

        # 3. Phone Events
        for e in payload.get("phoneUsageEvents", []):
            self.cursor.execute("INSERT INTO DrivingInsightsPhoneEvent (source_event_id, driving_insights_trip_id, start_time, start_time_epoch, end_time, end_time_epoch, call_state, waypoints_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                               (sid, di_id, self.format_ts(e.get("startTime")), e.get("startTimeEpoch"), self.format_ts(e.get("endTime")), e.get("endTimeEpoch"), e.get("callState"), self.compress_data(e.get("waypoints"))))

        # 4. Call Events
        for e in payload.get("callWhileMovingEvents", []):
            self.cursor.execute("INSERT INTO DrivingInsightsCallEvent (source_event_id, driving_insights_trip_id, start_time, start_time_epoch, end_time, end_time_epoch, min_traveled_speed_mps, max_traveled_speed_mps, hands_free_state, waypoints_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                               (sid, di_id, self.format_ts(e.get("startTime")), e.get("startTimeEpoch"), self.format_ts(e.get("endTime")), e.get("endTimeEpoch"), e.get("minTraveledSpeedMps"), e.get("maxTraveledSpeedMps"), e.get("handsFreeState"), self.compress_data(e.get("waypoints"))))

        # 5. Speeding Events
        for e in payload.get("speedingEvents", []):
            self.cursor.execute("INSERT INTO DrivingInsightsSpeedingEvent (source_event_id, driving_insights_trip_id, start_time, start_time_epoch, end_time, end_time_epoch, waypoints_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
                               (sid, di_id, self.format_ts(e.get("startTime")), e.get("startTimeEpoch"), self.format_ts(e.get("endTime")), e.get("endTimeEpoch"), self.compress_data(e.get("waypoints"))))

    def process_user_context(self, sid, uid, payload, is_manual=False):
        context = payload if is_manual else payload.get("userContext", {})
        criteria = ["MANUAL_REQUEST"] if is_manual else payload.get("criteria", [])
        loc = context.get("lastKnownLocation", {})
        
        self.cursor.execute("INSERT INTO UserContextHeader (source_event_id, sentiance_user_id, context_source_type, semantic_time, last_known_latitude, last_known_longitude, last_known_accuracy, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, GETDATE())",
                           (sid, uid, "MANUAL" if is_manual else "LISTENER", context.get("semanticTime"), loc.get("latitude"), loc.get("longitude"), loc.get("accuracy")))
        phid = self.cursor.execute("SELECT @@IDENTITY").fetchone()[0]

        for c in criteria:
            self.cursor.execute("INSERT INTO UserContextUpdateCriteria (user_context_payload_id, criteria_code) VALUES (?, ?)", (phid, c))

        for sig in ["home", "work"]:
            v = context.get(sig)
            if v:
                vloc = v.get("location", {})
                table = "UserHomeHistory" if sig == "home" else "UserWorkHistory"
                self.cursor.execute(f"INSERT INTO {table} (user_context_payload_id, significance, venue_type, latitude, longitude, accuracy) VALUES (?, ?, ?, ?, ?, ?)",
                                   (phid, sig.upper(), v.get("type"), vloc.get("latitude"), vloc.get("longitude"), vloc.get("accuracy")))

        for s in context.get("activeSegments", []):
            self.cursor.execute("INSERT INTO UserContextActiveSegmentDetail (user_context_payload_id, sentiance_user_id, segment_id, category, subcategory, segment_type, start_time, start_time_epoch, end_time, end_time_epoch, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE())",
                               (phid, uid, str(s.get("id")), s.get("category"), s.get("subcategory"), s.get("type"), self.format_ts(s.get("startTime")), s.get("startTimeEpoch"), self.format_ts(s.get("endTime")), s.get("endTimeEpoch")))
            sh_id = self.cursor.execute("SELECT @@IDENTITY").fetchone()[0]
            for a in s.get("attributes", []):
                self.cursor.execute("INSERT INTO UserContextSegmentAttribute (user_context_segment_history_id, attribute_name, attribute_value) VALUES (?, ?, ?)", (sh_id, a.get("name"), a.get("value")))

        for e in context.get("events", []):
            self.cursor.execute("INSERT INTO UserContextEventDetail (user_context_payload_id, sentiance_user_id, event_id, event_type, start_time, start_time_epoch, last_update_time, last_update_time_epoch, end_time, end_time_epoch, duration_in_seconds, is_provisional, transport_mode, distance_meters, occupant_role, transport_tags_json, location_latitude, location_longitude, location_accuracy, venue_significance, venue_type, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE())",
                               (phid, uid, e.get("id"), e.get("type"), self.format_ts(e.get("startTime")), e.get("startTimeEpoch"), self.format_ts(e.get("lastUpdateTime")), e.get("lastUpdateTimeEpoch"), self.format_ts(e.get("endTime")), e.get("endTimeEpoch"), e.get("durationInSeconds"), 1 if e.get("isProvisional") else 0, e.get("transportMode"), e.get("distance"), e.get("occupantRole"), self.compress_data(e.get("transportTags")), e.get("location", {}).get("latitude"), e.get("location", {}).get("longitude"), e.get("location", {}).get("accuracy"), e.get("venue", {}).get("significance"), e.get("venue", {}).get("type")))

    def process_timeline_events(self, sid, uid, payload):
        events = payload if isinstance(payload, list) else payload.get("events", [])
        for e in events:
            self.cursor.execute("INSERT INTO TimelineEventHistory (source_event_id, sentiance_user_id, event_id, event_type, start_time, start_time_epoch, last_update_time, last_update_time_epoch, end_time, end_time_epoch, duration_in_seconds, is_provisional, transport_mode, distance_meters, occupant_role, transport_tags_json, location_latitude, location_longitude, location_accuracy, venue_significance, venue_type, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE())",
                               (sid, uid, e.get("id"), e.get("type"), self.format_ts(e.get("startTime")), e.get("startTimeEpoch"), self.format_ts(e.get("lastUpdateTime")), e.get("lastUpdateTimeEpoch"), self.format_ts(e.get("endTime")), e.get("endTimeEpoch"), e.get("durationInSeconds"), 1 if e.get("isProvisional") else 0, e.get("transportMode"), e.get("distance"), e.get("occupantRole"), self.compress_data(e.get("transportTags")), e.get("location", {}).get("latitude"), e.get("location", {}).get("longitude"), e.get("location", {}).get("accuracy"), e.get("venue", {}).get("significance"), e.get("venue", {}).get("type")))
            if e.get("type") == "IN_TRANSPORT": self.upsert_trip(uid, e)

    def process_metadata(self, sid, uid, payload):
        label, val = payload.get("label"), payload.get("value")
        self.cursor.execute("INSERT INTO UserMetadata (sentiance_user_id, label, value, updated_at) VALUES (?, ?, ?, GETDATE())", (uid, label, str(val)))

    def process_crash_event(self, sid, uid, payload):
        l = payload.get("location", {})
        self.cursor.execute("INSERT INTO VehicleCrashEvent (source_event_id, sentiance_user_id, crash_time_epoch, latitude, longitude, accuracy, altitude, magnitude, speed_at_impact, delta_v, confidence, severity, detector_mode, preceding_locations_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                           (sid, uid, payload.get("time"), l.get("latitude"), l.get("longitude"), l.get("accuracy"), l.get("altitude"), payload.get("magnitude"), payload.get("speedAtImpact"), payload.get("deltaV"), payload.get("confidence"), payload.get("severity"), payload.get("detectorMode"), self.compress_data(payload.get("precedingLocations"))))

    def process_sdk_status(self, sid, uid, payload):
        self.cursor.execute("INSERT INTO SdkStatusHistory (source_event_id, sentiance_user_id, start_status, detection_status, location_permission, precise_location_granted, is_location_available, quota_status_wifi, quota_status_mobile, quota_status_disk, can_detect, captured_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE())",
                           (sid, uid, payload.get("startStatus"), payload.get("detectionStatus"), payload.get("locationPermission"), 1 if payload.get("isPreciseLocationPermGranted") else 0, 1 if payload.get("isLocationAvailable") else 0, payload.get("wifiQuotaStatus"), payload.get("mobileQuotaStatus"), payload.get("diskQuotaStatus"), 1 if payload.get("canDetect") else 0))

    def process_activity_history(self, sid, uid, payload):
        self.cursor.execute("INSERT INTO UserActivityHistory (source_event_id, sentiance_user_id, activity_type, trip_type, stationary_latitude, stationary_longitude, payload_json, captured_at) VALUES (?, ?, ?, ?, ?, ?, ?, GETDATE())",
                           (sid, uid, payload.get("activityType"), payload.get("tripType"), payload.get("stationaryLocation", {}).get("latitude"), payload.get("stationaryLocation", {}).get("longitude"), json.dumps(payload)))

    def process_technical_event(self, sid, uid, payload):
        self.cursor.execute("INSERT INTO TechnicalEventHistory (source_event_id, sentiance_user_id, technical_event_type, message, payload_json, captured_at) VALUES (?, ?, ?, ?, ?, GETDATE())",
                           (sid, uid, payload.get("type"), payload.get("message"), json.dumps(payload)))

    def run(self, batch_size=500):
        logger.info(f"Starting ETL Complete Pipeline (Batch: {batch_size})")
        self.connect()
        try:
            types = ("'DrivingInsights'", "'UserContextUpdate'", "'requestUserContext'", "'TimelineEvents'", "'VehicleCrash'", "'SDKStatus'", "'UserMetadata'", "'TechnicalEvent'", "'UserActivity'")
            query = f"SELECT TOP {batch_size} id, sentianceid, json, tipo FROM SentianceEventos WHERE is_processed = 0 AND tipo IN ({','.join(types)})"
            self.cursor.execute(query)
            rows = self.cursor.fetchall()
            for r_id, uid, r_json, tipo in rows:
                logger.info(f"Processing Record {r_id} ({tipo})")
                try:
                    p = json.loads(r_json)
                    st = self.format_ts(p.get("transportEvent", {}).get("startTime") or (p[0].get("startTime") if isinstance(p, list) and p else None) or p.get("startTime") or datetime.now().isoformat())
                    ref = p.get("transportEvent", {}).get("id") or (p[0].get("id") if isinstance(p, list) and p else None) or p.get("id") or str(r_id)
                    self.cursor.execute("INSERT INTO SdkSourceEvent (id, record_type, sentiance_user_id, source_time, source_event_ref, payload_hash, created_at) VALUES (?, ?, ?, ?, ?, ?, GETDATE())", (r_id, tipo, uid, st, ref, self.get_hash(r_json)))
                    sid = self.cursor.execute("SELECT @@IDENTITY").fetchone()[0]
                    if tipo == "DrivingInsights": self.process_driving_insights(sid, uid, p)
                    elif tipo in ["UserContextUpdate", "requestUserContext"]: self.process_user_context(sid, uid, p, tipo=="requestUserContext")
                    elif tipo == "TimelineEvents": self.process_timeline_events(sid, uid, p)
                    elif tipo == "UserMetadata": self.process_metadata(sid, uid, p)
                    elif tipo == "VehicleCrash": self.process_crash_event(sid, uid, p)
                    elif tipo == "SDKStatus": self.process_sdk_status(sid, uid, p)
                    elif tipo == "TechnicalEvent": self.process_technical_event(sid, uid, p)
                    elif tipo == "UserActivity": self.process_activity_history(sid, uid, p)
                    self.cursor.execute("UPDATE SentianceEventos SET is_processed = 1 WHERE id = ?", (r_id,))
                    self.conn.commit()
                except Exception as e:
                    self.conn.rollback()
                    logger.error(f"FAIL {r_id}: {e}")
                    self.log_error_to_db(r_id, uid, tipo, r_json, traceback.format_exc())
                    self.cursor.execute("UPDATE SentianceEventos SET is_processed = -1 WHERE id = ?", (r_id,))
                    self.conn.commit()
        finally: self.close()

if __name__ == "__main__":
    try: SentianceETL().run()
    except Exception as e: logger.error(f"Fatal: {e}")
