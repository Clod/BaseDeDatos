/*
===============================================================================
!!! DO NOT EXECUTE PROGRAMMATICALLY — HUMAN-ONLY ARTIFACT !!!
===============================================================================
No AI will ever run this file (migrate_prod_stage2.sql) against any database —
not production, not local, not via MCP, pyodbc, or any other path. It is a draft
artifact for a human to review and execute.
===============================================================================

===============================================================================
PRODUCTION DEPLOYMENT MIGRATION — VictaTMTK Stage-2 ETL
===============================================================================
Brings the production RDS `VictaTMTK` database to the state required to run the
Sentiance Stage-2 ETL (etl/sentiance_etl.py + etl/run_full_pipeline.py).

STATE VERIFIED AGAINST PROD RDS (2026-06-11):
  - The 22 Stage-2 domain tables do NOT exist yet (Trip, SdkSourceEvent,
    DrivingInsightsTrip, UserContext*, TimelineEventHistory, SdkStatusHistory,
    VehicleCrashEvent, UserOrganization, etc.).
  - `SentianceEventos` exists (landing zone, 67,342 rows) but has NO
    `is_processed` column — only the legacy `procesado` BIT, which is owned by
    other routines (Entregable §3.1.1) and MUST NOT be touched.
  - `SentianceEventos_Errors` already matches the Stage-2 layout — no change.
  - `SentianceEventos.json` is VARCHAR(MAX) (no truncation risk); `id` is INT
    (capacity note only — the ETL does not require BIGINT).
  - Prod `VictaTMTK` also already contains the legacy Movilidad-style tables
    (Transporte, Eventos, Conduccion, ...). Their names do not collide with any
    Stage-2 table, so the two coexist. (Confirm nothing else writes the Stage-2
    tables before enabling the ETL.)

-------------------------------------------------------------------------------
RUN ORDER (both steps are idempotent and safe to re-run):

  1. development/sql/init_db.sql
        Creates the 22 missing Stage-2 tables. Its `IF NOT EXISTS` guards SKIP
        the already-existing `SentianceEventos` and `SentianceEventos_Errors`,
        so it will NOT add `is_processed` — that is why step 2 is required.

  2. THIS FILE (migrate_prod_stage2.sql)
        Applies the deltas init_db.sql cannot: the `is_processed` column on the
        pre-existing landing table, plus the performance indexes.

-------------------------------------------------------------------------------
BEFORE RUNNING ON PROD:
  - Take a snapshot / backup of VictaTMTK.
  - Review the STEP 0 pre-flight output.
  - Run inside a transaction if your tooling supports DDL rollback.
  - After go-live, set the ETL log level to INFO (etl/sentiance_etl.py:67 is
    currently logging.DEBUG — far too verbose for a 67k-row run).
===============================================================================
*/

USE VictaTMTK;
GO

-------------------------------------------------------------------------------
-- STEP 0: Pre-flight checks (read-only — review the output before continuing)
-------------------------------------------------------------------------------
PRINT '=== STEP 0: Pre-flight ===';

SELECT 'Stage-2 tables present (of 22 expected)' AS check_name, COUNT(*) AS value
FROM sys.tables
WHERE name IN (
    'SdkSourceEvent','UserMetadata','Trip','DrivingInsightsTrip',
    'DrivingInsightsHarshEvent','DrivingInsightsPhoneEvent','DrivingInsightsCallEvent',
    'DrivingInsightsSpeedingEvent','DrivingInsightsWrongWayDrivingEvent',
    'UserContextHeader','UserContextUpdateCriteria','UserHomeHistory','UserWorkHistory',
    'UserContextActiveSegmentDetail','UserContextSegmentAttribute','UserContextEventDetail',
    'TimelineEventHistory','UserActivityHistory','TechnicalEventHistory',
    'VehicleCrashEvent','SdkStatusHistory','UserOrganization'
);

SELECT 'SentianceEventos.is_processed exists' AS check_name,
       COUNT(*) AS value
FROM sys.columns
WHERE object_id = OBJECT_ID('dbo.SentianceEventos') AND name = 'is_processed';

SELECT 'Landing rows total' AS check_name, COUNT(*) AS value FROM dbo.SentianceEventos;
GO

-------------------------------------------------------------------------------
-- STEP 1: Add `is_processed` to the existing landing zone.
--
--   NOT NULL DEFAULT 0 backfills ALL existing rows to 0, so the ETL will pick
--   up the entire 67k-row backlog on the first run. The legacy `procesado`
--   column is intentionally left untouched (owned by other routines).
-------------------------------------------------------------------------------
PRINT '=== STEP 1: SentianceEventos.is_processed ===';

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.SentianceEventos') AND name = 'is_processed'
)
BEGIN
    ALTER TABLE dbo.SentianceEventos
        ADD is_processed SMALLINT NOT NULL
            CONSTRAINT DF_SentianceEventos_is_processed DEFAULT 0;
    PRINT '  Added SentianceEventos.is_processed (existing rows defaulted to 0).';
END
ELSE
    PRINT '  SentianceEventos.is_processed already exists — skipped.';
GO

-------------------------------------------------------------------------------
-- STEP 2A: ETL hot-path indexes — REQUIRED before the first backlog run.
--
--   These back the lookups the ETL performs for every record (trip upserts,
--   the orphan-parent guard, child-event parent resolution) and the queue
--   scan. Without them, a 67k-row backlog run does repeated full table scans.
-------------------------------------------------------------------------------
PRINT '=== STEP 2A: ETL hot-path indexes ===';

-- Queue scan: WHERE is_processed = 0 AND tipo IN (...). Filtered index stays
-- small once the backlog drains.
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='IX_SentianceEventos_pending' AND object_id=OBJECT_ID('dbo.SentianceEventos'))
    CREATE INDEX IX_SentianceEventos_pending ON dbo.SentianceEventos(id) WHERE is_processed = 0;

-- Trip upsert lookup. The ETL MERGE keys on (canonical_transport_event_id,
-- sentiance_user_id) — see UNIQUE note at the bottom of this file.
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='IX_Trip_canonical_user' AND object_id=OBJECT_ID('dbo.Trip'))
    CREATE INDEX IX_Trip_canonical_user ON dbo.Trip(canonical_transport_event_id, sentiance_user_id);

-- DrivingInsightsTrip lookup: orphan-parent guard + child-event resolution +
-- the Movilidad bridge all filter on this pair.
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='IX_DITrip_canonical_user' AND object_id=OBJECT_ID('dbo.DrivingInsightsTrip'))
    CREATE INDEX IX_DITrip_canonical_user ON dbo.DrivingInsightsTrip(canonical_transport_event_id, sentiance_user_id);

-- Child-event tables are read back by the bridge via driving_insights_trip_id.
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='IX_HarshEvent_ditrip' AND object_id=OBJECT_ID('dbo.DrivingInsightsHarshEvent'))
    CREATE INDEX IX_HarshEvent_ditrip ON dbo.DrivingInsightsHarshEvent(driving_insights_trip_id);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='IX_PhoneEvent_ditrip' AND object_id=OBJECT_ID('dbo.DrivingInsightsPhoneEvent'))
    CREATE INDEX IX_PhoneEvent_ditrip ON dbo.DrivingInsightsPhoneEvent(driving_insights_trip_id);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='IX_CallEvent_ditrip' AND object_id=OBJECT_ID('dbo.DrivingInsightsCallEvent'))
    CREATE INDEX IX_CallEvent_ditrip ON dbo.DrivingInsightsCallEvent(driving_insights_trip_id);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='IX_SpeedingEvent_ditrip' AND object_id=OBJECT_ID('dbo.DrivingInsightsSpeedingEvent'))
    CREATE INDEX IX_SpeedingEvent_ditrip ON dbo.DrivingInsightsSpeedingEvent(driving_insights_trip_id);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='IX_WrongWayEvent_ditrip' AND object_id=OBJECT_ID('dbo.DrivingInsightsWrongWayDrivingEvent'))
    CREATE INDEX IX_WrongWayEvent_ditrip ON dbo.DrivingInsightsWrongWayDrivingEvent(driving_insights_trip_id);

-- Movilidad bridge reads the latest context / crashes per user.
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='IX_UCHeader_user' AND object_id=OBJECT_ID('dbo.UserContextHeader'))
    CREATE INDEX IX_UCHeader_user ON dbo.UserContextHeader(sentiance_user_id);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='IX_CrashEvent_user' AND object_id=OBJECT_ID('dbo.VehicleCrashEvent'))
    CREATE INDEX IX_CrashEvent_user ON dbo.VehicleCrashEvent(sentiance_user_id);
GO

-------------------------------------------------------------------------------
-- STEP 2B: Analytic + FK-join indexes (Entregable §3.7).
--
--   These serve business queries and audit JOINs, not the ETL write path. They
--   may optionally be created AFTER the initial backlog load to speed the bulk
--   insert (fewer indexes to maintain during the 67k-row run). Idempotent
--   either way.
-------------------------------------------------------------------------------
PRINT '=== STEP 2B: Analytic + FK-join indexes ===';

-- §3.7-1: user filter on the landing zone.
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='IX_SentianceEventos_sentianceid' AND object_id=OBJECT_ID('dbo.SentianceEventos'))
    CREATE INDEX IX_SentianceEventos_sentianceid ON dbo.SentianceEventos(sentianceid);

-- §3.7-4: time-range analytics + audit on the source event index.
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='IX_SdkSourceEvent_source_time' AND object_id=OBJECT_ID('dbo.SdkSourceEvent'))
    CREATE INDEX IX_SdkSourceEvent_source_time ON dbo.SdkSourceEvent(source_time);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='IX_SdkSourceEvent_eventos_id' AND object_id=OBJECT_ID('dbo.SdkSourceEvent'))
    CREATE INDEX IX_SdkSourceEvent_eventos_id ON dbo.SdkSourceEvent(sentiance_eventos_id);

-- §3.7-3: "trips / timeline of user X in date range".
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='IX_Trip_user_time' AND object_id=OBJECT_ID('dbo.Trip'))
    CREATE INDEX IX_Trip_user_time ON dbo.Trip(sentiance_user_id, start_time_epoch);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='IX_TimelineEvent_user_time' AND object_id=OBJECT_ID('dbo.TimelineEventHistory'))
    CREATE INDEX IX_TimelineEvent_user_time ON dbo.TimelineEventHistory(sentiance_user_id, start_time_epoch);

-- §3.7-6: sdk_source_event_id on child tables (audit "what did this raw event produce?").
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='IX_DITrip_src' AND object_id=OBJECT_ID('dbo.DrivingInsightsTrip'))
    CREATE INDEX IX_DITrip_src ON dbo.DrivingInsightsTrip(sdk_source_event_id);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='IX_DITrip_trip' AND object_id=OBJECT_ID('dbo.DrivingInsightsTrip'))
    CREATE INDEX IX_DITrip_trip ON dbo.DrivingInsightsTrip(trip_id);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='IX_TimelineEvent_src' AND object_id=OBJECT_ID('dbo.TimelineEventHistory'))
    CREATE INDEX IX_TimelineEvent_src ON dbo.TimelineEventHistory(sdk_source_event_id);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='IX_UCHeader_src' AND object_id=OBJECT_ID('dbo.UserContextHeader'))
    CREATE INDEX IX_UCHeader_src ON dbo.UserContextHeader(sdk_source_event_id);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='IX_CrashEvent_src' AND object_id=OBJECT_ID('dbo.VehicleCrashEvent'))
    CREATE INDEX IX_CrashEvent_src ON dbo.VehicleCrashEvent(sdk_source_event_id);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='IX_SdkStatus_src' AND object_id=OBJECT_ID('dbo.SdkStatusHistory'))
    CREATE INDEX IX_SdkStatus_src ON dbo.SdkStatusHistory(sdk_source_event_id);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='IX_UserActivity_src' AND object_id=OBJECT_ID('dbo.UserActivityHistory'))
    CREATE INDEX IX_UserActivity_src ON dbo.UserActivityHistory(sdk_source_event_id);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='IX_TechnicalEvent_src' AND object_id=OBJECT_ID('dbo.TechnicalEventHistory'))
    CREATE INDEX IX_TechnicalEvent_src ON dbo.TechnicalEventHistory(sdk_source_event_id);

-- Harsh/Phone/Call/Speeding/WrongWay also carry sdk_source_event_id for audit.
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='IX_HarshEvent_src' AND object_id=OBJECT_ID('dbo.DrivingInsightsHarshEvent'))
    CREATE INDEX IX_HarshEvent_src ON dbo.DrivingInsightsHarshEvent(sdk_source_event_id);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='IX_PhoneEvent_src' AND object_id=OBJECT_ID('dbo.DrivingInsightsPhoneEvent'))
    CREATE INDEX IX_PhoneEvent_src ON dbo.DrivingInsightsPhoneEvent(sdk_source_event_id);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='IX_CallEvent_src' AND object_id=OBJECT_ID('dbo.DrivingInsightsCallEvent'))
    CREATE INDEX IX_CallEvent_src ON dbo.DrivingInsightsCallEvent(sdk_source_event_id);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='IX_SpeedingEvent_src' AND object_id=OBJECT_ID('dbo.DrivingInsightsSpeedingEvent'))
    CREATE INDEX IX_SpeedingEvent_src ON dbo.DrivingInsightsSpeedingEvent(sdk_source_event_id);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='IX_WrongWayEvent_src' AND object_id=OBJECT_ID('dbo.DrivingInsightsWrongWayDrivingEvent'))
    CREATE INDEX IX_WrongWayEvent_src ON dbo.DrivingInsightsWrongWayDrivingEvent(sdk_source_event_id);

-- UserContext child tables: FK-join columns used by analytics and the bridge.
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='IX_UCCriteria_payload' AND object_id=OBJECT_ID('dbo.UserContextUpdateCriteria'))
    CREATE INDEX IX_UCCriteria_payload ON dbo.UserContextUpdateCriteria(user_context_payload_id);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='IX_UCEventDetail_payload' AND object_id=OBJECT_ID('dbo.UserContextEventDetail'))
    CREATE INDEX IX_UCEventDetail_payload ON dbo.UserContextEventDetail(user_context_payload_id);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='IX_UCSegment_payload' AND object_id=OBJECT_ID('dbo.UserContextActiveSegmentDetail'))
    CREATE INDEX IX_UCSegment_payload ON dbo.UserContextActiveSegmentDetail(user_context_payload_id);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='IX_UCSegmentAttr_segment' AND object_id=OBJECT_ID('dbo.UserContextSegmentAttribute'))
    CREATE INDEX IX_UCSegmentAttr_segment ON dbo.UserContextSegmentAttribute(user_context_active_segment_detail_id);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='IX_UserHome_payload' AND object_id=OBJECT_ID('dbo.UserHomeHistory'))
    CREATE INDEX IX_UserHome_payload ON dbo.UserHomeHistory(user_context_payload_id);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='IX_UserWork_payload' AND object_id=OBJECT_ID('dbo.UserWorkHistory'))
    CREATE INDEX IX_UserWork_payload ON dbo.UserWorkHistory(user_context_payload_id);

-- UserMetadata lookups (incl. the 'organizacion' → UserOrganization path).
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='IX_UserMetadata_user' AND object_id=OBJECT_ID('dbo.UserMetadata'))
    CREATE INDEX IX_UserMetadata_user ON dbo.UserMetadata(sentiance_user_id);
GO

-------------------------------------------------------------------------------
-- STEP 3: Post-migration verification (read-only)
-------------------------------------------------------------------------------
PRINT '=== STEP 3: Verification ===';

SELECT 'is_processed present' AS check_name, COUNT(*) AS value
FROM sys.columns WHERE object_id = OBJECT_ID('dbo.SentianceEventos') AND name = 'is_processed';

SELECT 'rows ready to process (is_processed = 0)' AS check_name, COUNT(*) AS value
FROM dbo.SentianceEventos WHERE is_processed = 0;

SELECT 'Stage-2 indexes created (this migration, IX_*)' AS check_name, COUNT(*) AS value
FROM sys.indexes WHERE name LIKE 'IX_%'
  AND object_id IN (
    OBJECT_ID('dbo.SentianceEventos'), OBJECT_ID('dbo.SdkSourceEvent'), OBJECT_ID('dbo.Trip'),
    OBJECT_ID('dbo.DrivingInsightsTrip'), OBJECT_ID('dbo.DrivingInsightsHarshEvent'),
    OBJECT_ID('dbo.DrivingInsightsPhoneEvent'), OBJECT_ID('dbo.DrivingInsightsCallEvent'),
    OBJECT_ID('dbo.DrivingInsightsSpeedingEvent'), OBJECT_ID('dbo.DrivingInsightsWrongWayDrivingEvent'),
    OBJECT_ID('dbo.UserContextHeader'), OBJECT_ID('dbo.UserContextUpdateCriteria'),
    OBJECT_ID('dbo.UserContextEventDetail'), OBJECT_ID('dbo.UserContextActiveSegmentDetail'),
    OBJECT_ID('dbo.UserContextSegmentAttribute'), OBJECT_ID('dbo.UserHomeHistory'),
    OBJECT_ID('dbo.UserWorkHistory'), OBJECT_ID('dbo.TimelineEventHistory'),
    OBJECT_ID('dbo.UserActivityHistory'), OBJECT_ID('dbo.TechnicalEventHistory'),
    OBJECT_ID('dbo.VehicleCrashEvent'), OBJECT_ID('dbo.SdkStatusHistory'),
    OBJECT_ID('dbo.UserMetadata')
  );
GO

PRINT 'Migration complete. Do a controlled first run:';
PRINT '  python etl/sentiance_etl.py        (single batch — inspect SentianceEventos_Errors)';
PRINT '  then python etl/run_full_pipeline.py (drain the backlog)';
GO

/*
===============================================================================
NOTES / DECISIONS (read before running)
===============================================================================

1. UNIQUE index on Trip — DEFERRED, not applied here.
   Entregable §3.7-7 recommends a UNIQUE index on Trip(canonical_transport_event_id).
   Two corrections:
     a) The ETL's MERGE keys on the PAIR (canonical_transport_event_id,
        sentiance_user_id), not canonical alone — a unique index must be on the
        pair, or it could reject legitimate rows.
     b) The ETL is single-threaded, so MERGE cannot race; a unique constraint is
        not required for correctness today. IX_Trip_canonical_user (non-unique,
        created above) already provides the lookup performance.
   If/when you run multiple ETL workers concurrently, promote it:
       CREATE UNIQUE INDEX UX_Trip_canonical_user
           ON dbo.Trip(canonical_transport_event_id, sentiance_user_id);
   (Safe to create now since the table starts empty, but validate the first
    backlog run produces no unique violations before relying on it.)

2. UNIQUE index on UserContextActiveSegmentDetail — INTENTIONALLY OMITTED.
   Entregable §3.7-8 recommends UNIQUE(sentiance_user_id, segment_id). This is
   INCOMPATIBLE with the current ETL: process_user_context does a plain INSERT
   (not a MERGE) for active segments, and the same user re-lists the same active
   segment on every context update. A unique index would reject those repeats
   and send rows to SentianceEventos_Errors. Only add it if the ETL is changed
   to upsert this table.

3. CHECK constraints (Entregable §3.8.2, e.g. chk_criteria_code with
   'MANUAL_REQUEST') are NOT created here — optional hardening, out of scope for
   go-live. If added later, chk_criteria_code MUST include 'MANUAL_REQUEST'
   (the ETL inserts it for requestUserContext).

4. FK ON DELETE/UPDATE policies (Entregable §3.8.1) are not added; init_db.sql's
   existing FKs on Trip suffice for launch.
===============================================================================
*/
