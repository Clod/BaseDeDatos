/*
VictaTMTK - Complete Database Schema (Sentiance 2026)
=====================================================
Ref: Entregable.md & MapeoSDK_BD.md
*/

USE master;
GO

IF NOT EXISTS (SELECT * FROM sys.databases WHERE name = 'VictaTMTK')
BEGIN
    CREATE DATABASE VictaTMTK;
END
GO

USE VictaTMTK;
GO

-------------------------------------------------------------------------------
-- STAGE 1: LANDING ZONE & AUDIT
-------------------------------------------------------------------------------

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'SentianceEventos')
BEGIN
    CREATE TABLE SentianceEventos (
        id BIGINT IDENTITY(1,1) PRIMARY KEY,
        sentianceid VARCHAR(64),
        json NVARCHAR(MAX),
        tipo VARCHAR(32),
        created_at DATETIME2(3) DEFAULT GETDATE(),
        is_processed BIT DEFAULT 0,
        procesado BIT DEFAULT 0,
        app_version VARCHAR(32)
    );
END

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'SentianceEventos_Errors')
BEGIN
    CREATE TABLE SentianceEventos_Errors (
        error_id BIGINT IDENTITY(1,1) PRIMARY KEY,
        original_id BIGINT NOT NULL,
        sentiance_user_id VARCHAR(64),
        tipo VARCHAR(32),
        raw_json NVARCHAR(MAX),
        error_message NVARCHAR(MAX),
        failed_at DATETIME2(3) DEFAULT GETDATE()
    );
END

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'SdkSourceEvent')
BEGIN
    CREATE TABLE SdkSourceEvent (
        source_event_id BIGINT IDENTITY(1,1) PRIMARY KEY,
        id BIGINT NOT NULL,
        record_type VARCHAR(32),
        sentiance_user_id VARCHAR(64),
        source_time DATETIME2(3),
        source_event_ref VARCHAR(64),
        payload_hash VARCHAR(64),
        created_at DATETIME2(3) DEFAULT GETDATE()
    );
END

-------------------------------------------------------------------------------
-- STAGE 2: DOMAIN MODEL
-------------------------------------------------------------------------------

-- 1. Metadata
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'UserMetadata')
BEGIN
    CREATE TABLE UserMetadata (
        metadata_id BIGINT IDENTITY(1,1) PRIMARY KEY,
        sentiance_user_id VARCHAR(64) NOT NULL,
        label VARCHAR(255),
        value NVARCHAR(MAX),
        updated_at DATETIME2(3) DEFAULT GETDATE()
    );
END

-- 2. Central Trip Table
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Trip')
BEGIN
    CREATE TABLE Trip (
        trip_id BIGINT IDENTITY(1,1) PRIMARY KEY,
        sentiance_user_id VARCHAR(64) NOT NULL,
        canonical_transport_event_id VARCHAR(64) NOT NULL,
        first_seen_from VARCHAR(32),
        transport_mode VARCHAR(32),
        start_time DATETIME2(3),
        start_time_epoch BIGINT,
        last_update_time DATETIME2(3),
        last_update_time_epoch BIGINT,
        end_time DATETIME2(3),
        end_time_epoch BIGINT,
        duration_in_seconds NUMERIC(10, 0),
        distance_meters NUMERIC(12, 2),
        occupant_role VARCHAR(32),
        is_provisional BIT DEFAULT 0,
        transport_tags_json VARBINARY(MAX),
        waypoints_json VARBINARY(MAX),
        start_location_json VARCHAR(255), -- Geocoded address placeholder
        end_location_json VARCHAR(255),   -- Geocoded address placeholder
        created_at DATETIME2(3) DEFAULT GETDATE(),
        updated_at DATETIME2(3) DEFAULT GETDATE()
    );
END

-- 3. Driving Insights
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'DrivingInsightsTrip')
BEGIN
    CREATE TABLE DrivingInsightsTrip (
        driving_insights_trip_id BIGINT IDENTITY(1,1) PRIMARY KEY,
        source_event_id BIGINT NOT NULL,
        trip_id BIGINT,
        sentiance_user_id VARCHAR(64),
        canonical_transport_event_id VARCHAR(64),
        smooth_score NUMERIC(4, 3),
        focus_score NUMERIC(4, 3),
        legal_score NUMERIC(4, 3),
        call_while_moving_score NUMERIC(4, 3),
        overall_score NUMERIC(4, 3),
        harsh_braking_score NUMERIC(4, 3),
        harsh_turning_score NUMERIC(4, 3),
        harsh_acceleration_score NUMERIC(4, 3),
        wrong_way_driving_score NUMERIC(4, 3),
        attention_score NUMERIC(4, 3),
        distance_meters NUMERIC(12, 2),
        occupant_role VARCHAR(32),
        transport_tags_json VARBINARY(MAX),
        created_at DATETIME2(3) DEFAULT GETDATE()
    );
END

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'DrivingInsightsHarshEvent')
BEGIN
    CREATE TABLE DrivingInsightsHarshEvent (
        harsh_event_id BIGINT IDENTITY(1,1) PRIMARY KEY,
        source_event_id BIGINT NOT NULL,
        driving_insights_trip_id BIGINT NOT NULL,
        start_time DATETIME2(3),
        start_time_epoch BIGINT,
        end_time DATETIME2(3),
        end_time_epoch BIGINT,
        magnitude NUMERIC(6, 3),
        confidence NUMERIC(4, 3),
        harsh_type VARCHAR(32),
        waypoints_json VARBINARY(MAX)
    );
END

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'DrivingInsightsPhoneEvent')
BEGIN
    CREATE TABLE DrivingInsightsPhoneEvent (
        phone_event_id BIGINT IDENTITY(1,1) PRIMARY KEY,
        source_event_id BIGINT NOT NULL,
        driving_insights_trip_id BIGINT NOT NULL,
        start_time DATETIME2(3),
        start_time_epoch BIGINT,
        end_time DATETIME2(3),
        end_time_epoch BIGINT,
        call_state VARCHAR(32),
        waypoints_json VARBINARY(MAX)
    );
END

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'DrivingInsightsCallEvent')
BEGIN
    CREATE TABLE DrivingInsightsCallEvent (
        call_event_id BIGINT IDENTITY(1,1) PRIMARY KEY,
        source_event_id BIGINT NOT NULL,
        driving_insights_trip_id BIGINT NOT NULL,
        start_time DATETIME2(3),
        start_time_epoch BIGINT,
        end_time DATETIME2(3),
        end_time_epoch BIGINT,
        min_traveled_speed_mps NUMERIC(7, 2),
        max_traveled_speed_mps NUMERIC(7, 2),
        hands_free_state VARCHAR(32),
        waypoints_json VARBINARY(MAX)
    );
END

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'DrivingInsightsSpeedingEvent')
BEGIN
    CREATE TABLE DrivingInsightsSpeedingEvent (
        speeding_event_id BIGINT IDENTITY(1,1) PRIMARY KEY,
        source_event_id BIGINT NOT NULL,
        driving_insights_trip_id BIGINT NOT NULL,
        start_time DATETIME2(3),
        start_time_epoch BIGINT,
        end_time DATETIME2(3),
        end_time_epoch BIGINT,
        waypoints_json VARBINARY(MAX)
    );
END

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'DrivingInsightsWrongWayDrivingEvent')
BEGIN
    CREATE TABLE DrivingInsightsWrongWayDrivingEvent (
        wrong_way_event_id BIGINT IDENTITY(1,1) PRIMARY KEY,
        source_event_id BIGINT NOT NULL,
        driving_insights_trip_id BIGINT NOT NULL,
        start_time DATETIME2(3),
        start_time_epoch BIGINT,
        end_time DATETIME2(3),
        end_time_epoch BIGINT,
        waypoints_json VARBINARY(MAX)
    );
END

-- 4. User Context
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'UserContextHeader')
BEGIN
    CREATE TABLE UserContextHeader (
        user_context_payload_id BIGINT IDENTITY(1,1) PRIMARY KEY,
        source_event_id BIGINT NOT NULL,
        sentiance_user_id VARCHAR(64),
        context_source_type VARCHAR(32),
        semantic_time VARCHAR(32),
        last_known_latitude DECIMAL(10, 8),
        last_known_longitude DECIMAL(11, 8),
        last_known_accuracy NUMERIC(12, 2),
        created_at DATETIME2(3) DEFAULT GETDATE()
    );
END

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'UserContextUpdateCriteria')
BEGIN
    CREATE TABLE UserContextUpdateCriteria (
        user_context_update_criteria_id BIGINT IDENTITY(1,1) PRIMARY KEY,
        user_context_payload_id BIGINT NOT NULL,
        criteria_code VARCHAR(32)
    );
END

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'UserHomeHistory')
BEGIN
    CREATE TABLE UserHomeHistory (
        user_home_history_id BIGINT IDENTITY(1,1) PRIMARY KEY,
        user_context_payload_id BIGINT NOT NULL,
        significance VARCHAR(32),
        venue_type VARCHAR(32),
        latitude DECIMAL(10, 8),
        longitude DECIMAL(11, 8),
        accuracy NUMERIC(12, 2)
    );
END

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'UserWorkHistory')
BEGIN
    CREATE TABLE UserWorkHistory (
        user_work_history_id BIGINT IDENTITY(1,1) PRIMARY KEY,
        user_context_payload_id BIGINT NOT NULL,
        significance VARCHAR(32),
        venue_type VARCHAR(32),
        latitude DECIMAL(10, 8),
        longitude DECIMAL(11, 8),
        accuracy NUMERIC(12, 2)
    );
END

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'UserContextActiveSegmentDetail')
BEGIN
    CREATE TABLE UserContextActiveSegmentDetail (
        user_context_segment_history_id BIGINT IDENTITY(1,1) PRIMARY KEY,
        user_context_payload_id BIGINT NOT NULL,
        sentiance_user_id VARCHAR(64),
        segment_id VARCHAR(64),
        category VARCHAR(32),
        subcategory VARCHAR(32),
        segment_type VARCHAR(32),
        start_time DATETIME2(3),
        start_time_epoch BIGINT,
        end_time DATETIME2(3),
        end_time_epoch BIGINT,
        created_at DATETIME2(3) DEFAULT GETDATE()
    );
END

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'UserContextSegmentAttribute')
BEGIN
    CREATE TABLE UserContextSegmentAttribute (
        user_context_segment_attr_id BIGINT IDENTITY(1,1) PRIMARY KEY,
        user_context_segment_history_id BIGINT NOT NULL,
        attribute_name VARCHAR(64),
        attribute_value NUMERIC(18, 4)
    );
END

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'UserContextEventDetail')
BEGIN
    CREATE TABLE UserContextEventDetail (
        user_context_event_history_id BIGINT IDENTITY(1,1) PRIMARY KEY,
        user_context_payload_id BIGINT NOT NULL,
        sentiance_user_id VARCHAR(64),
        event_id VARCHAR(64),
        event_type VARCHAR(32),
        start_time DATETIME2(3),
        start_time_epoch BIGINT,
        last_update_time DATETIME2(3),
        last_update_time_epoch BIGINT,
        end_time DATETIME2(3),
        end_time_epoch BIGINT,
        duration_in_seconds NUMERIC(10, 0),
        is_provisional BIT,
        transport_mode VARCHAR(32),
        distance_meters NUMERIC(12, 2),
        occupant_role VARCHAR(32),
        transport_tags_json VARBINARY(MAX),
        location_latitude DECIMAL(10, 8),
        location_longitude DECIMAL(11, 8),
        location_accuracy NUMERIC(12, 2),
        venue_significance VARCHAR(32),
        venue_type VARCHAR(32),
        created_at DATETIME2(3) DEFAULT GETDATE()
    );
END

-- 5. Timeline & System History
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'TimelineEventHistory')
BEGIN
    CREATE TABLE TimelineEventHistory (
        timeline_event_history_id BIGINT IDENTITY(1,1) PRIMARY KEY,
        source_event_id BIGINT NOT NULL,
        sentiance_user_id VARCHAR(64),
        event_id VARCHAR(64),
        event_type VARCHAR(32),
        start_time DATETIME2(3),
        start_time_epoch BIGINT,
        last_update_time DATETIME2(3),
        last_update_time_epoch BIGINT,
        end_time DATETIME2(3),
        end_time_epoch BIGINT,
        duration_in_seconds NUMERIC(10, 0),
        is_provisional BIT,
        transport_mode VARCHAR(32),
        distance_meters NUMERIC(12, 2),
        occupant_role VARCHAR(32),
        transport_tags_json VARBINARY(MAX),
        location_latitude DECIMAL(10, 8),
        location_longitude DECIMAL(11, 8),
        location_accuracy NUMERIC(12, 2),
        venue_significance VARCHAR(32),
        venue_type VARCHAR(32),
        created_at DATETIME2(3) DEFAULT GETDATE()
    );
END

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'UserActivityHistory')
BEGIN
    CREATE TABLE UserActivityHistory (
        user_activity_history_id BIGINT IDENTITY(1,1) PRIMARY KEY,
        source_event_id BIGINT NOT NULL,
        sentiance_user_id VARCHAR(64),
        activity_type VARCHAR(32),
        trip_type VARCHAR(32),
        stationary_latitude DECIMAL(10, 8),
        stationary_longitude DECIMAL(11, 8),
        payload_json NVARCHAR(MAX),
        captured_at DATETIME2(3) DEFAULT GETDATE()
    );
END

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'TechnicalEventHistory')
BEGIN
    CREATE TABLE TechnicalEventHistory (
        technical_event_history_id BIGINT IDENTITY(1,1) PRIMARY KEY,
        source_event_id BIGINT NOT NULL,
        sentiance_user_id VARCHAR(64),
        technical_event_type VARCHAR(32),
        message NVARCHAR(MAX),
        payload_json NVARCHAR(MAX),
        captured_at DATETIME2(3) DEFAULT GETDATE()
    );
END

-- 6. Safety Events
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'VehicleCrashEvent')
BEGIN
    CREATE TABLE VehicleCrashEvent (
        vehicle_crash_event_id BIGINT IDENTITY(1,1) PRIMARY KEY,
        source_event_id BIGINT NOT NULL,
        sentiance_user_id VARCHAR(64),
        crash_time_epoch BIGINT,
        latitude DECIMAL(10, 8),
        longitude DECIMAL(11, 8),
        accuracy NUMERIC(12, 2),
        altitude NUMERIC(10, 2),
        magnitude NUMERIC(6, 3),
        speed_at_impact NUMERIC(7, 2),
        delta_v NUMERIC(7, 2),
        confidence NUMERIC(4, 3),
        severity VARCHAR(32),
        detector_mode VARCHAR(32),
        preceding_locations_json VARBINARY(MAX)
    );
END

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'SdkStatusHistory')
BEGIN
    CREATE TABLE SdkStatusHistory (
        sdk_status_history_id BIGINT IDENTITY(1,1) PRIMARY KEY,
        source_event_id BIGINT NOT NULL,
        sentiance_user_id VARCHAR(64),
        start_status VARCHAR(32),
        detection_status VARCHAR(32),
        location_permission VARCHAR(32),
        precise_location_granted BIT,
        is_location_available BIT,
        quota_status_wifi VARCHAR(32),
        quota_status_mobile VARCHAR(32),
        quota_status_disk VARCHAR(32),
        can_detect BIT,
        captured_at DATETIME2(3) DEFAULT GETDATE()
    );
END

PRINT 'Full relational schema (Stage 2) successfully initialized.';
