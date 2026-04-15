import os
import json
import gzip
import pyodbc
import hashlib
import logging
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class SentianceETL:
    def __init__(self):
        # Configuration retrieved from environment variables
        server = os.getenv("DB_SERVER")
        port = os.getenv("DB_PORT")
        user = os.getenv("DB_USER")
        password = os.getenv("DB_PASSWORD")
        database = os.getenv("DB_NAME")

        if not all([server, port, user, password, database]):
            raise ValueError(
                "Missing database configuration in environment variables. "
                "Ensure DB_SERVER, DB_PORT, DB_USER, DB_PASSWORD, and DB_NAME are set."
            )

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
        try:
            self.conn = pyodbc.connect(self.conn_str)
            self.cursor = self.conn.cursor()
            logger.info("Connected to database successfully.")
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise

    def close(self):
        if self.conn:
            self.conn.close()

    def compress_data(self, data):
        """Compress JSON-serializable data using gzip for VARBINARY(MAX) columns."""
        if data is None:
            return None
        json_str = json.dumps(data)
        return gzip.compress(json_str.encode("utf-8"))

    def get_hash(self, text):
        """Generate SHA-256 hash for payload deduplication."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def upsert_trip(self, sentiance_user_id, transport_event):
        """Consolidate trip data into the central Trip table."""
        canonical_id = transport_event.get("id")
        if not canonical_id:
            return None

        # SQL Server MERGE for Trip
        sql = """
        MERGE Trip AS target
        USING (SELECT ? AS tid, ? AS uid) AS source
        ON target.canonical_transport_event_id = source.tid AND target.sentiance_user_id = source.uid
        WHEN MATCHED THEN
            UPDATE SET 
                last_update_time = ?, 
                last_update_time_epoch = ?,
                end_time = ?,
                end_time_epoch = ?,
                duration_in_seconds = ?,
                distance_meters = ?,
                transport_mode = ?,
                occupant_role = ?,
                is_provisional = ?,
                updated_at = GETDATE()
        WHEN NOT MATCHED THEN
            INSERT (sentiance_user_id, canonical_transport_event_id, first_seen_from, 
                    start_time, start_time_epoch, last_update_time, last_update_time_epoch,
                    end_time, end_time_epoch, duration_in_seconds, distance_meters, 
                    transport_mode, occupant_role, is_provisional, 
                    transport_tags_json, waypoints_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE(), GETDATE());
        """

        # Prepare parameters
        params = [
            canonical_id,
            sentiance_user_id,
            # Update fields
            transport_event.get("lastUpdateTime"),
            transport_event.get("lastUpdateTimeEpoch"),
            transport_event.get("endTime"),
            transport_event.get("endTimeEpoch"),
            transport_event.get("durationInSeconds"),
            transport_event.get("distance"),
            transport_event.get("transportMode"),
            transport_event.get("occupantRole"),
            1 if transport_event.get("isProvisional") else 0,
            # Insert fields
            sentiance_user_id,
            canonical_id,
            "ETL_PROCESS",
            transport_event.get("startTime"),
            transport_event.get("startTimeEpoch"),
            transport_event.get("lastUpdateTime"),
            transport_event.get("lastUpdateTimeEpoch"),
            transport_event.get("endTime"),
            transport_event.get("endTimeEpoch"),
            transport_event.get("durationInSeconds"),
            transport_event.get("distance"),
            transport_event.get("transportMode"),
            transport_event.get("occupantRole"),
            1 if transport_event.get("isProvisional") else 0,
            self.compress_data(transport_event.get("transportTags")),
            self.compress_data(transport_event.get("waypoints")),
        ]

        self.cursor.execute(sql, params)

        # Get the internal trip_id
        self.cursor.execute(
            "SELECT trip_id FROM Trip WHERE canonical_transport_event_id = ? AND sentiance_user_id = ?",
            (canonical_id, sentiance_user_id),
        )
        res = self.cursor.fetchone()
        return res[0] if res else None

    def process_driving_insights(self, source_event_id, sentiance_user_id, payload):
        """
        Handler for 'DrivingInsights' (DrivingInsightsReady) events.
        Maps transport metrics and safety scores into the relational model.
        """
        transport = payload.get("transportEvent", {})
        scores = payload.get("safetyScores", {})

        # 1. Sync with central Trip table to ensure relational integrity
        trip_id = self.upsert_trip(sentiance_user_id, transport)

        # 2. Insert the main DrivingInsights metrics
        # Scores are mapped to NUMERIC(4,3) columns [0, 1]
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
            source_event_id,
            trip_id,
            sentiance_user_id,
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
        ]
        self.cursor.execute(sql, params)
        di_trip_id = self.cursor.execute("SELECT @@IDENTITY").fetchone()[0]

        # 3. Process Harsh Events (Braking, Acceleration, Turning)
        # Each event becomes a row in the child table for granular analysis.
        harsh_events = payload.get("harshDrivingEvents", [])
        for event in harsh_events:
            self.cursor.execute(
                """
                INSERT INTO DrivingInsightsHarshEvent (
                    source_event_id, driving_insights_trip_id, start_time, start_time_epoch,
                    end_time, end_time_epoch, magnitude, confidence, harsh_type, waypoints_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    source_event_id,
                    di_trip_id,
                    event.get("startTime"),
                    event.get("startTimeEpoch"),
                    event.get("endTime"),
                    event.get("endTimeEpoch"),
                    event.get("magnitude"),
                    event.get("confidence"),
                    event.get("type"),
                    self.compress_data(event.get("waypoints")),
                ),
            )

    def process_user_context(
        self, source_event_id, sentiance_user_id, payload, is_manual=False
    ):
        """
        Handler for 'UserContextUpdate' and 'requestUserContext'.
        Processes semantic time, user locations (home/work), and active life segments.
        """
        # 1. Normalize payload structure
        # requestUserContext is 'flat', while UserContextUpdate has a 'userContext' wrapper.
        if is_manual:
            context = payload
            criteria = ["MANUAL_REQUEST"]
        else:
            context = payload.get("userContext", {})
            criteria = payload.get("criteria", [])

        # 2. Insert UserContextHeader (Root of the context update)
        sql_header = """
        INSERT INTO UserContextHeader (
            source_event_id, sentiance_user_id, context_source_type, semantic_time,
            last_known_latitude, last_known_longitude, last_known_accuracy, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, GETDATE())
        """
        loc = context.get("lastKnownLocation", {})
        header_params = [
            source_event_id,
            sentiance_user_id,
            "MANUAL" if is_manual else "LISTENER",
            context.get("semanticTime"),
            loc.get("latitude"),
            loc.get("longitude"),
            loc.get("accuracy"),
        ]
        self.cursor.execute(sql_header, header_params)
        payload_id = self.cursor.execute("SELECT @@IDENTITY").fetchone()[0]

        # 3. Store Update Criteria (Why did this context change?)
        for code in criteria:
            self.cursor.execute(
                "INSERT INTO UserContextUpdateCriteria (user_context_payload_id, criteria_code) VALUES (?, ?)",
                (payload_id, code),
            )

        # 4. Store Venue History (Evolution of Home/Work locations)
        for significance in ["home", "work"]:
            venue = context.get(significance)
            if venue:
                v_loc = venue.get("location", {})
                table = (
                    "UserHomeHistory" if significance == "home" else "UserWorkHistory"
                )
                self.cursor.execute(
                    f"""
                    INSERT INTO {table} (user_context_payload_id, significance, venue_type, latitude, longitude, accuracy)
                    VALUES (?, ?, ?, ?, ?, ?)
                """,
                    (
                        payload_id,
                        significance.upper(),
                        venue.get("type"),
                        v_loc.get("latitude"),
                        v_loc.get("longitude"),
                        v_loc.get("accuracy"),
                    ),
                )

        # 5. Store Active Segments (Driving, Shopping, Early Bird, etc.)
        for segment in context.get("activeSegments", []):
            self.cursor.execute(
                """
                INSERT INTO UserContextActiveSegmentDetail (
                    user_context_payload_id, sentiance_user_id, segment_id, category, subcategory, segment_type,
                    start_time, start_time_epoch, end_time, end_time_epoch, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE())
            """,
                (
                    payload_id,
                    sentiance_user_id,
                    str(segment.get("id")),
                    segment.get("category"),
                    segment.get("subcategory"),
                    segment.get("type"),
                    segment.get("startTime"),
                    segment.get("startTimeEpoch"),
                    segment.get("endTime"),
                    segment.get("endTimeEpoch"),
                ),
            )

            seg_history_id = self.cursor.execute("SELECT @@IDENTITY").fetchone()[0]

            # Store Segment Attributes (Score values for the segments)
            for attr in segment.get("attributes", []):
                self.cursor.execute(
                    """
                    INSERT INTO UserContextSegmentAttribute (user_context_segment_history_id, attribute_name, attribute_value)
                    VALUES (?, ?, ?)
                """,
                    (seg_history_id, attr.get("name"), attr.get("value")),
                )

        # 6. Store Context Events (Current active activity: stationary, transport, etc.)
        for event in context.get("events", []):
            self.cursor.execute(
                """
                INSERT INTO UserContextEventDetail (
                    user_context_payload_id, sentiance_user_id, event_id, event_type,
                    start_time, start_time_epoch, last_update_time, last_update_time_epoch,
                    end_time, end_time_epoch, duration_in_seconds, is_provisional,
                    transport_mode, distance_meters, occupant_role, transport_tags_json,
                    location_latitude, location_longitude, location_accuracy,
                    venue_significance, venue_type, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE())
            """,
                (
                    payload_id,
                    sentiance_user_id,
                    event.get("id"),
                    event.get("type"),
                    event.get("startTime"),
                    event.get("startTimeEpoch"),
                    event.get("lastUpdateTime"),
                    event.get("lastUpdateTimeEpoch"),
                    event.get("endTime"),
                    event.get("endTimeEpoch"),
                    event.get("durationInSeconds"),
                    1 if event.get("isProvisional") else 0,
                    event.get("transportMode"),
                    event.get("distance"),
                    event.get("occupantRole"),
                    self.compress_data(event.get("transportTags")),
                    event.get("location", {}).get("latitude"),
                    event.get("location", {}).get("longitude"),
                    event.get("location", {}).get("accuracy"),
                    event.get("venue", {}).get("significance"),
                    event.get("venue", {}).get("type"),
                ),
            )

    def process_timeline_events(self, source_event_id, sentiance_user_id, payload):
        """
        Handler for 'TimelineEvents' (TimelineUpdate) events.
        Processes an array of historical events and syncs transport events with the Trip table.
        """
        # TimelineEvents payload is usually a JSON array directly or wrapped.
        events = payload if isinstance(payload, list) else payload.get("events", [])

        for event in events:
            # 1. Store in historical timeline table
            self.cursor.execute(
                """
                INSERT INTO TimelineEventHistory (
                    source_event_id, sentiance_user_id, event_id, event_type,
                    start_time, start_time_epoch, last_update_time, last_update_time_epoch,
                    end_time, end_time_epoch, duration_in_seconds, is_provisional,
                    transport_mode, distance_meters, occupant_role, transport_tags_json,
                    location_latitude, location_longitude, location_accuracy,
                    venue_significance, venue_type, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE())
            """,
                (
                    source_event_id,
                    sentiance_user_id,
                    event.get("id"),
                    event.get("type"),
                    event.get("startTime"),
                    event.get("startTimeEpoch"),
                    event.get("lastUpdateTime"),
                    event.get("lastUpdateTimeEpoch"),
                    event.get("endTime"),
                    event.get("endTimeEpoch"),
                    event.get("durationInSeconds"),
                    1 if event.get("isProvisional") else 0,
                    event.get("transportMode"),
                    event.get("distance"),
                    event.get("occupantRole"),
                    self.compress_data(event.get("transportTags")),
                    event.get("location", {}).get("latitude"),
                    event.get("location", {}).get("longitude"),
                    event.get("location", {}).get("accuracy"),
                    event.get("venue", {}).get("significance"),
                    event.get("venue", {}).get("type"),
                ),
            )

            # 2. If it's a transport event, sync it with the central Trip registry
            if event.get("type") == "IN_TRANSPORT":
                self.upsert_trip(sentiance_user_id, event)

    def process_crash_event(self, source_event_id, sentiance_user_id, payload):
        """
        Handler for 'VehicleCrash' (CrashEvent) events.
        Stores impact data and preceding locations for safety analysis.
        """
        loc = payload.get("location", {})
        self.cursor.execute(
            """
            INSERT INTO VehicleCrashEvent (
                source_event_id, sentiance_user_id, crash_time_epoch,
                latitude, longitude, accuracy, altitude,
                magnitude, speed_at_impact, delta_v, confidence,
                severity, detector_mode, preceding_locations_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                source_event_id,
                sentiance_user_id,
                payload.get("time"),
                loc.get("latitude"),
                loc.get("longitude"),
                loc.get("accuracy"),
                loc.get("altitude"),
                payload.get("magnitude"),
                payload.get("speedAtImpact"),
                payload.get("deltaV"),
                payload.get("confidence"),
                payload.get("severity"),
                payload.get("detectorMode"),
                self.compress_data(payload.get("precedingLocations")),
            ),
        )

    def process_sdk_status(self, source_event_id, sentiance_user_id, payload):
        """
        Handler for 'SDKStatus' (SdkStatus) events.
        Captures operational health and permission states.
        """
        self.cursor.execute(
            """
            INSERT INTO SdkStatusHistory (
                source_event_id, sentiance_user_id, start_status, detection_status,
                location_permission, precise_location_granted, is_location_available,
                quota_status_wifi, quota_status_mobile, quota_status_disk,
                can_detect, captured_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE())
        """,
            (
                source_event_id,
                sentiance_user_id,
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

    def run(self, batch_size=50):
        self.connect()
        try:
            # Fetch unprocessed records
            # We filter by 'tipo' to only process implemented handlers
            implemented_types = (
                "'DrivingInsights'",
                "'UserContextUpdate'",
                "'requestUserContext'",
                "'TimelineEvents'",
                "'VehicleCrash'",
                "'SDKStatus'",
            )
            query = f"SELECT TOP {batch_size} id, sentianceid, json, tipo FROM SentianceEventos WHERE is_processed = 0 AND tipo IN ({','.join(implemented_types)})"

            self.cursor.execute(query)
            rows = self.cursor.fetchall()

            if not rows:
                logger.info("No records to process.")
                return

            for row in rows:
                raw_id, sentiance_id, raw_json, tipo = row
                logger.info(f"Processing record {raw_id} of type {tipo}")

                try:
                    payload = json.loads(raw_json)

                    # 1. Create Audit Entry (SdkSourceEvent)
                    # We extract source_time and ref from the payload if possible
                    source_time_str = (
                        payload.get("transportEvent", {}).get("startTime")
                        or (
                            payload[0].get("startTime")
                            if isinstance(payload, list) and payload
                            else None
                        )
                        or payload.get("startTime")
                        or datetime.now().isoformat()
                    )
                    source_ref = (
                        payload.get("transportEvent", {}).get("id")
                        or (
                            payload[0].get("id")
                            if isinstance(payload, list) and payload
                            else None
                        )
                        or payload.get("id")
                        or str(raw_id)
                    )

                    self.cursor.execute(
                        """
                        INSERT INTO SdkSourceEvent (id, record_type, sentiance_user_id, source_time, source_event_ref, payload_hash, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, GETDATE())
                    """,
                        (
                            raw_id,
                            tipo,
                            sentiance_id,
                            source_time_str[:23],
                            source_ref,
                            self.get_hash(raw_json),
                        ),
                    )

                    source_event_id = self.cursor.execute(
                        "SELECT @@IDENTITY"
                    ).fetchone()
                    source_event_id = source_event_id[0] if source_event_id else None

                    # 2. Route by type to specific handlers
                    if tipo == "DrivingInsights":
                        self.process_driving_insights(
                            source_event_id, sentiance_id, payload
                        )
                    elif tipo in ["UserContextUpdate", "requestUserContext"]:
                        self.process_user_context(
                            source_event_id,
                            sentiance_id,
                            payload,
                            is_manual=(tipo == "requestUserContext"),
                        )
                    elif tipo == "TimelineEvents":
                        self.process_timeline_events(
                            source_event_id, sentiance_id, payload
                        )
                    elif tipo == "VehicleCrash":
                        self.process_crash_event(source_event_id, sentiance_id, payload)
                    elif tipo == "SDKStatus":
                        self.process_sdk_status(source_event_id, sentiance_id, payload)

                    # 3. Mark as successfully processed
                    self.cursor.execute(
                        "UPDATE SentianceEventos SET is_processed = 1 WHERE id = ?",
                        (raw_id,),
                    )

                    self.conn.commit()
                    logger.info(f"Successfully processed record {raw_id}")

                except Exception as e:
                    self.conn.rollback()
                    logger.error(f"Error processing record {raw_id}: {e}")
                    # Mark as failed to avoid infinite retries on malformed data
                    self.cursor.execute(
                        "UPDATE SentianceEventos SET is_processed = -1 WHERE id = ?",
                        (raw_id,),
                    )
                    self.conn.commit()

        finally:
            self.close()


if __name__ == "__main__":
    # The ETL now automatically loads credentials from the .env file
    etl = SentianceETL()
    etl.run()
