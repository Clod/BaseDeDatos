# Trip Data Flow Architecture

The following Mermaid flowchart illustrates how the raw event data "travels" and is processed from the entry point (`SentianceEventos`) down into the canonical `Trip` and its related insight tables, according to the `Entregable.md` documentation.

```mermaid
flowchart TB
    %% Definitions
    Raw[(SentianceEventos)]
    Source[SdkSourceEvent]
    
    %% Intermediate Payload Tables
    subgraph Intermediate Processing
        Timeline[TimelineEventHistory]
        ContextPayload[UserContextHeader]
        ContextEvents[UserContextEventDetail]
    end
    
    %% Canonical Trip
    CanonicalTrip(((Trip)))
    
    %% Insights and Events during a Trip
    subgraph Driving Insights & Events
        DITrip[DrivingInsightsTrip]
        Crash[VehicleCrashEvent]
        
        Harsh[DrivingInsightsHarshEvent]
        Phone[DrivingInsightsPhoneEvent]
        Call[DrivingInsightsCallEvent]
        Speeding[DrivingInsightsSpeedingEvent]
        WrongWay[DrivingInsightsWrongWayDrivingEvent]
    end

    %% Flow Steps
    Raw -->|"Normalizes into"| Source
    
    %% From Source to branches
    Source -->|"Generates"| Timeline
    Source -->|"Generates"| ContextPayload
    Source -->|"Generates directly"| DITrip
    Source -->|"Generates"| Crash
    
    %% Context processing
    ContextPayload -->|"Breaks down into"| ContextEvents
    
    %% Feeding into the canonical Trip table
    Timeline -->|"Feeds into"| CanonicalTrip
    ContextEvents -->|"Feeds into<br/>(IN_TRANSPORT / STATIONARY)"| CanonicalTrip
    
    %% Trip to Driving Insights Relationship
    CanonicalTrip -.-|"Is ancestor of<br/>(matches canonical_transport_event_id)"| DITrip
    
    %% Driving Insights granular events
    DITrip -->|"Records"| Harsh
    DITrip -->|"Records"| Phone
    DITrip -->|"Records"| Call
    DITrip -->|"Records"| Speeding
    DITrip -->|"Records"| WrongWay
    
    %% Styling
    style Raw fill:#1E293B,stroke:#94A3B8,color:#fff
    style CanonicalTrip fill:#047857,stroke:#34D399,stroke-width:3px,color:#fff
    style DITrip fill:#4338CA,stroke:#8B5CF6,color:#fff
```

## Data Flow Explanation

1. **Ingestion & Normalization**
    *   All data lands as raw JSON in the `SentianceEventos` table.
    *   It is then processed and normalized into the `SdkSourceEvent` table.

2. **Splitting the Data**
    *   From `SdkSourceEvent`, the data branches out into specific domain tables:
        *   **Timeline events:** Go to `TimelineEventHistory`.
        *   **User Context events:** The full payload goes to `UserContextHeader`, and the inner events array is broken out into `UserContextEventDetail`.
        *   **Vehicle Crashes:** Are stored directly into `VehicleCrashEvent`.
        *   **Completed trip scores:** Land safely in `DrivingInsightsTrip`.

3. **Consolidating the Trip**
    *   Both `TimelineEventHistory` and `UserContextEventDetail` feed into the canonical **`Trip`** model to define the start, end, location, and transport mode of the journey.

4. **Insights Breakdown**
    *   Once `DrivingInsightsTrip` receives scores for a given transport, it acts as the parent repository for anomalous driving activities.
    *   It generates and records granular incident records reflecting exactly what happened during the drive (`Speeding`, `Harsh Events`, `Phone Usage`, `Calls while moving`, and `Wrong-way driving`).
