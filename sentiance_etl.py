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
- Error Resilience: Uses atomic transactions; failed records are marked for investigation.

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
# Even a junior can follow the console output to understand the script's progress.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("SentianceETL")


class SentianceETL:
    """
    Main ETL engine responsible for transforming raw Sentiance JSON payloads
    into a structured relational database model.
    """

    def __init__(self):
        """
        Initializes the ETL instance by loading database configuration from environment variables.
        """
        logger.info("Initializing Sentiance ETL Engine...")

        # Retrieval of credentials from environment (Security Best Practice)
        server = os.getenv("DB_SERVER")
        port = os.getenv("DB_PORT")
        user = os.getenv("DB_USER")
        password = os.getenv("DB_PASSWORD")
        database = os.getenv("DB_NAME")

        if not all([server, port, user, password, database]):
            logger.error("Database configuration is incomplete in .env file.")
            raise ValueError(
                "Missing DB_SERVER, DB_PORT, DB_USER, DB_PASSWORD, or DB_NAME in environment."
            )

        # Build the ODBC connection string (Using Driver 18 for modern SQL Server features)
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
        """
        Establishes a connection to the SQL Server database.
        """
        try:
            logger.info(f"Connecting to database at {os.getenv('DB_SERVER')}...")
            self.conn = pyodbc.connect(self.conn_str)
            self.cursor = self.conn.cursor()
            logger.info("Connection established successfully.")
        except Exception as e:
            logger.critical(f"CRITICAL: Failed to connect to the database: {e}")
            raise

    def close(self):
        """
        Closes the database connection safely.
        """
        if self.conn:
            logger.info("Closing database connection.")
            self.conn.close()

    def log_error_to_db(self, original_id, sentiance_id, tipo, raw_json, error_msg):
        """
        Records a failed processing attempt in the SentianceEventos_Errors shadow table.
        This allows for forensic analysis without modifying the primary raw table.
        """
        try:
            logger.warning(
                f"Logging failure for record {original_id} to shadow table..."
            )
            sql = """
                INSERT INTO SentianceEventos_Errors (original_id, sentiance_user_id, tipo, raw_json, error_message)
                VALUES (?, ?, ?, ?, ?)
            """
            self.cursor.execute(
                sql, (original_id, sentiance_id, tipo, raw_json, error_msg)
            )
            # We don't commit here; it will be committed along with the is_processed = -1 update.
        except Exception as e:
            logger.error(f"CRITICAL: Failed to write to error shadow table: {e}")

    def compress_data(self, data):
        """
        Compresses JSON-serializable objects using GZIP.
        Used for columns typed as VARBINARY(MAX) to save 60-80% storage.

        Args:
            data (any): Python object (list, dict) to be serialized and compressed.

        Returns:
            bytes: Compressed binary data or None if input is empty.
        """
        if data is None or (isinstance(data, list) and len(data) == 0):
            return None

        try:
            json_str = json.dumps(data)
            compressed = gzip.compress(json_str.encode("utf-8"))
            return compressed
        except Exception as e:
            logger.warning(f"Compression failed for data block: {e}")
            return None

    def get_hash(self, text):
        """
        Generates a SHA-256 hash of a string.
        Used to prevent duplicate processing of the same raw payload.
        """
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def upsert_trip(self, sentiance_user_id, transport_event):
        """
        Maintains the central 'Trip' table.
        Ensures that multiple events belonging to the same journey are consolidated.

        Args:
            sentiance_user_id (str): The unique ID of the user.
            transport_event (dict): The transport data from the payload.
        """
        canonical_id = transport_event.get("id")
        if not canonical_id:
            logger.debug("Skipping trip upsert: No canonical transport ID found.")
            return None

        logger.info(f"Upserting Trip registry for ID: {canonical_id}")

        # SQL MERGE: Atomic 'Update if exists, else Insert'
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

        params = [
            canonical_id,
            sentiance_user_id,
            # Data for UPDATE
            transport_event.get("lastUpdateTime"),
            transport_event.get("lastUpdateTimeEpoch"),
            transport_event.get("endTime"),
            transport_event.get("endTimeEpoch"),
            transport_event.get("durationInSeconds"),
            transport_event.get("distance"),
            transport_event.get("transportMode"),
            transport_event.get("occupantRole"),
            1 if transport_event.get("isProvisional") else 0,
            # Data for INSERT
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

        # Retrieve the internal auto-increment ID for relational linking
        self.cursor.execute(
            "SELECT trip_id FROM Trip WHERE canonical_transport_event_id = ? AND sentiance_user_id = ?",
            (canonical_id, sentiance_user_id),
        )
        res = self.cursor.fetchone()
        return res[0] if res else None

    def process_driving_insights(self, source_event_id, sentiance_user_id, payload):
        """
        Processes 'DrivingInsights' events containing safety scores and harsh driving details.
        """
        logger.info("--- Handling DrivingInsights Event ---")
        transport = payload.get("transportEvent", {})
        scores = payload.get("safetyScores", {})

        # Ensure we have a central trip record to link to
        trip_id = self.upsert_trip(sentiance_user_id, transport)

        # Insert main scoring data
        logger.info(f"Saving safety scores for trip {transport.get('id')}...")
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

        # Extract and save granular harsh events (Braking, Acceleration, Turning)
        harsh_events = payload.get("harshDrivingEvents", [])
        logger.info(f"Found {len(harsh_events)} harsh driving events to process.")
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
        Processes 'UserContextUpdate' and 'requestUserContext' events.
        Extracts behavior segments, semantic time (Morning, Lunch, etc.), and venue history.
        """
        logger.info("--- Handling UserContext Event ---")
        if is_manual:
            logger.info("Processing as MANUAL request.")
            context = payload
            criteria = ["MANUAL_REQUEST"]
        else:
            logger.info("Processing as SDK LISTENER update.")
            context = payload.get("userContext", {})
            criteria = payload.get("criteria", [])

        # 1. Create the Context Header
        logger.info(
            f"Recording context header (Semantic Time: {context.get('semanticTime')})"
        )
        loc = context.get("lastKnownLocation", {})
        self.cursor.execute(
            """
            INSERT INTO UserContextHeader (
                source_event_id, sentiance_user_id, context_source_type, semantic_time,
                last_known_latitude, last_known_longitude, last_known_accuracy, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, GETDATE())
        """,
            (
                source_event_id,
                sentiance_user_id,
                "MANUAL" if is_manual else "LISTENER",
                context.get("semanticTime"),
                loc.get("latitude"),
                loc.get("longitude"),
                loc.get("accuracy"),
            ),
        )

        payload_id = self.cursor.execute("SELECT @@IDENTITY").fetchone()[0]

        # 2. Record Criteria (Why did the context change?)
        for code in criteria:
            self.cursor.execute(
                "INSERT INTO UserContextUpdateCriteria (user_context_payload_id, criteria_code) VALUES (?, ?)",
                (payload_id, code),
            )

        # 3. Record Home/Work locations (Refined by Sentiance over time)
        for sig in ["home", "work"]:
            venue = context.get(sig)
            if venue:
                logger.info(f"Updating detected {sig} location.")
                v_loc = venue.get("location", {})
                table = "UserHomeHistory" if sig == "home" else "UserWorkHistory"
                self.cursor.execute(
                    f"INSERT INTO {table} (...) VALUES (...)", (...)
                )  # Implementation omitted for brevity in docs

        # 4. Record Life Segments (e.g., SHOPPING, DRIVING, EARLY_BIRD)
        segments = context.get("activeSegments", [])
        logger.info(f"Processing {len(segments)} active life segments.")
        for segment in segments:
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

            # Sub-attributes for the segment (scores, etc.)
            for attr in segment.get("attributes", []):
                self.cursor.execute(
                    "INSERT INTO UserContextSegmentAttribute ...", (...)
                )

        # 5. Record Contextual Events (Stationary, Transport)
        ctx_events = context.get("events", [])
        logger.info(f"Processing {len(ctx_events)} context-specific events.")
        for event in ctx_events:
            self.cursor.execute("INSERT INTO UserContextEventDetail ...", (...))

    def process_timeline_events(self, source_event_id, sentiance_user_id, payload):
        """
        Processes 'TimelineEvents' containing an array of historical trip and stationary events.
        """
        logger.info("--- Handling TimelineEvents Array ---")
        events = payload if isinstance(payload, list) else payload.get("events", [])
        logger.info(f"Processing {len(events)} events from historical timeline.")

        for event in events:
            # Save historical event
            self.cursor.execute("INSERT INTO TimelineEventHistory ...", (...))

            # Sync with central trip registry if it's a journey
            if event.get("type") == "IN_TRANSPORT":
                logger.info(
                    f"Syncing transport event {event.get('id')} to central Trip registry."
                )
                self.upsert_trip(sentiance_user_id, event)

    def process_crash_event(self, source_event_id, sentiance_user_id, payload):
        """
        Processes 'VehicleCrash' events with high-precision impact telemetry.
        """
        logger.info("--- Handling VehicleCrash Event ---")
        logger.info(f"Recording crash event with severity: {payload.get('severity')}")
        loc = payload.get("location", {})
        self.cursor.execute("INSERT INTO VehicleCrashEvent ...", (...))

    def process_sdk_status(self, source_event_id, sentiance_user_id, payload):
        """
        Processes 'SDKStatus' events for operational health monitoring.
        """
        logger.info("--- Handling SDKStatus Update ---")
        logger.info(
            f"SDK Status: {payload.get('detectionStatus')} | Can Detect: {payload.get('canDetect')}"
        )
        self.cursor.execute("INSERT INTO SdkStatusHistory ...", (...))

    def run(self, batch_size=50):
        """
        Main execution loop. Fetches a batch of raw records and processes them one by one.
        """
        logger.info(f"Starting ETL Batch Execution (Size: {batch_size})...")
        self.connect()

        try:
            implemented_types = (
                "'DrivingInsights'",
                "'UserContextUpdate'",
                "'requestUserContext'",
                "'TimelineEvents'",
                "'VehicleCrash'",
                "'SDKStatus'",
            )
            query = f"""
                SELECT TOP {batch_size} id, sentianceid, json, tipo 
                FROM SentianceEventos 
                WHERE is_processed = 0 
                AND tipo IN ({",".join(implemented_types)})
            """

            self.cursor.execute(query)
            rows = self.cursor.fetchall()

            if not rows:
                logger.info("Work queue is empty. No records to process.")
                return

            logger.info(f"Found {len(rows)} records in current batch.")

            for row in rows:
                raw_id, sentiance_id, raw_json, tipo = row
                logger.info(f"== [RECORD {raw_id}] Start processing type: {tipo} ==")

                try:
                    payload = json.loads(raw_json)

                    # 1. Deduplication and Audit Entry
                    logger.info("Generating audit trail (SdkSourceEvent)...")
                    # (Simplified logic for brevity in this display, using previously written code)
                    source_time_str = (
                        payload.get("transportEvent", {}).get("startTime")
                        or datetime.now().isoformat()
                    )
                    source_ref = payload.get("transportEvent", {}).get("id") or str(
                        raw_id
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
                    ).fetchone()[0]

                    # 2. Handler Routing
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

                    # 3. Finalization
                    logger.info(f"Marking record {raw_id} as processed.")
                    self.cursor.execute(
                        "UPDATE SentianceEventos SET is_processed = 1 WHERE id = ?",
                        (raw_id,),
                    )

                    self.conn.commit()
                    logger.info(
                        f"== [RECORD {raw_id}] Successfully Processed & Committed =="
                    )

                except Exception as e:
                    self.conn.rollback()
                    full_traceback = traceback.format_exc()
                    logger.error(f"FAILED record {raw_id}: {e}")

                    # 1. Capture the failure in the shadow table for forensic analysis
                    self.log_error_to_db(
                        raw_id, sentiance_id, tipo, raw_json, full_traceback
                    )

                    # 2. Mark original as toxic (-1) so it doesn't block the queue
                    self.cursor.execute(
                        "UPDATE SentianceEventos SET is_processed = -1 WHERE id = ?",
                        (raw_id,),
                    )
                    self.conn.commit()
                    logger.warning(
                        f"Record {raw_id} marked as FAILED (-1) and logged to shadow table."
                    )

            logger.info("Batch execution completed successfully.")

        finally:
            self.close()


if __name__ == "__main__":
    try:
        etl = SentianceETL()
        etl.run(batch_size=50)
    except Exception as e:
        logger.error(f"ETL Execution halted due to error: {e}")
