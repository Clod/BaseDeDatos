# Diseño de Base de Datos - Eventos Sentiance

## 1. Contexto y Origen de Datos (Payloads)

Este modelo de base de datos está diseñado para almacenar estructuradamente la información recolectada por el **SDK de Sentiance** en aplicaciones móviles.

La información ingresa al backend mediante **eventos recibidos a través de los *listeners* u oyentes del SDK en el dispositivo móvil** (principalmente bajo la implementación de React Native u otros lenguajes nativos de la App). 

**Puntos Importantes:**
- **Solo Listeners:** No se consolida información proveniente de los volcados diarios (Offloads). El stream es un pipeline directo donde el Frontend emite el payload JSON directamente al backend.
- **Formato Crudo (Raw):** El JSON almacenado inicialmente en la tabla `SentianceEventos` es el payload exacto emitido por el SDK, sin agregados, sobres ni modificaciones de parte del backend.
- **Múltiples Fuentes de Viajes (`Trip`):** La entidad central `Trip` (viaje) no proviene de un solo payload. Es una tabla normalizada alimentada por múltiples fuentes: Eventos temporales (`TimelineEvent` o del `UserContext`) especialmente útiles para viajes cortos, peatonales, bicicletas o colectivos, y objetos de `DrivingInsights` para trayectos motorizados de autos/motos.

---

## 2. Diagrama Entidad-Relación (ER)

```mermaid
erDiagram
	direction TB
	SentianceEventos {
		int id PK 
		varchar sentianceid
		datetime fechahora
		text json
		varchar tipo
		datetime created_at
		bit procesado
		varchar app_version
	}

	SdkSourceEvent {
		bigint source_event_id PK 
		int id FK 
		varchar record_type
		varchar sentiance_user_id
		datetime source_time
		varchar source_event_ref
		varchar payload_hash
		datetime created_at
	}

	TimelineEventHistory {
		bigint timeline_event_history_id PK 
		bigint source_event_id FK 
		varchar sentiance_user_id
		varchar event_id
		varchar event_type
		datetime start_time
		bigint start_time_epoch
		datetime last_update_time
		bigint last_update_time_epoch
		datetime end_time
		bigint end_time_epoch
		numeric duration_in_seconds
		boolean is_provisional
		varchar transport_mode
		numeric distance_meters
		varchar occupant_role
		text transport_tags_json
		decimal location_latitude
		decimal location_longitude
		numeric location_accuracy
		varchar venue_significance
		varchar venue_type
		text waypoints_json
		datetime created_at
	}

	UserContextHeader {
		bigint user_context_payload_id PK 
		bigint source_event_id FK 
		varchar sentiance_user_id
		varchar context_source_type
		varchar semantic_time
		decimal last_known_latitude
		decimal last_known_longitude
		numeric last_known_accuracy
		datetime created_at
	}

	UserContextEventDetail {
		bigint user_context_event_history_id PK 
		bigint user_context_payload_id FK 
		varchar sentiance_user_id
		varchar event_id
		varchar event_type
		datetime start_time
		bigint start_time_epoch
		datetime last_update_time
		bigint last_update_time_epoch
		datetime end_time
		bigint end_time_epoch
		numeric duration_in_seconds
		boolean is_provisional
		varchar transport_mode
		numeric distance_meters
		varchar occupant_role
		text transport_tags_json
		decimal location_latitude
		decimal location_longitude
		numeric location_accuracy
		varchar venue_significance
		varchar venue_type
		datetime created_at
	}

	UserContextActiveSegmentDetail {
		bigint user_context_segment_history_id PK 
		bigint user_context_payload_id FK 
		varchar sentiance_user_id
		varchar segment_id
		varchar category
		varchar subcategory
		varchar segment_type
		datetime start_time
		bigint start_time_epoch
		datetime end_time
		bigint end_time_epoch
		datetime created_at
	}

	UserContextSegmentAttribute {
		bigint user_context_segment_attribute_id PK 
		bigint user_context_segment_history_id FK 
		varchar attribute_name
		numeric attribute_value
	}

	UserHomeHistory {
		bigint user_home_history_id PK 
		bigint user_context_payload_id FK 
		varchar significance
		varchar venue_type
		decimal latitude
		decimal longitude
		numeric accuracy
	}

	UserWorkHistory {
		bigint user_work_history_id PK 
		bigint user_context_payload_id FK 
		varchar significance
		varchar venue_type
		decimal latitude
		decimal longitude
		numeric accuracy
	}

	UserContextUpdateCriteria {
		bigint user_context_update_criteria_id PK 
		bigint user_context_payload_id FK 
		varchar criteria_code
	}

	DrivingInsightsTrip {
		bigint driving_insights_trip_id PK 
		bigint source_event_id FK 
		bigint trip_id FK 
		varchar sentiance_user_id
		varchar transport_event_id
		numeric smooth_score
		numeric focus_score
		numeric legal_score
		numeric call_while_moving_score
		numeric overall_score
		numeric harsh_braking_score
		numeric harsh_turning_score
		numeric harsh_acceleration_score
		numeric wrong_way_driving_score
		numeric attention_score
		numeric distance_meters
		text waypoints_json
		datetime created_at
	}

	DrivingInsightsHarshEvent {
		bigint harsh_event_id PK 
		bigint source_event_id FK 
		bigint driving_insights_trip_id FK 
		datetime start_time
		bigint start_time_epoch
		datetime end_time
		bigint end_time_epoch
		numeric magnitude
		numeric confidence
		varchar harsh_type
		text waypoints_json
	}

	DrivingInsightsPhoneEvent {
		bigint phone_event_id PK 
		bigint source_event_id FK 
		bigint driving_insights_trip_id FK 
		datetime start_time
		bigint start_time_epoch
		datetime end_time
		bigint end_time_epoch
		varchar call_state
		text waypoints_json
	}

	DrivingInsightsCallEvent {
		bigint call_event_id PK 
		bigint source_event_id FK 
		bigint driving_insights_trip_id FK 
		datetime start_time
		bigint start_time_epoch
		datetime end_time
		bigint end_time_epoch
		numeric min_traveled_speed_mps
		numeric max_traveled_speed_mps
		varchar hands_free_state
		text waypoints_json
	}

	DrivingInsightsSpeedingEvent {
		bigint speeding_event_id PK 
		bigint source_event_id FK 
		bigint driving_insights_trip_id FK 
		datetime start_time
		bigint start_time_epoch
		datetime end_time
		bigint end_time_epoch
		text waypoints_json
	}

	DrivingInsightsWrongWayDrivingEvent {
		bigint wrong_way_event_id PK 
		bigint source_event_id FK 
		bigint driving_insights_trip_id FK 
		datetime start_time
		bigint start_time_epoch
		datetime end_time
		bigint end_time_epoch
		text waypoints_json
	}

	VehicleCrashEvent {
		bigint vehicle_crash_event_id PK 
		bigint source_event_id FK 
		varchar sentiance_user_id
		bigint crash_time_epoch
		decimal latitude
		decimal longitude
		numeric accuracy
		numeric altitude
		numeric magnitude
		numeric speed_at_impact
		numeric delta_v
		numeric confidence
		varchar severity
		varchar detector_mode
	}

	SdkStatusHistory {
		bigint sdk_status_history_id PK 
		bigint source_event_id FK 
		varchar sentiance_user_id
		varchar location_permission
		boolean precise_location_granted
		varchar detection_status
		boolean is_quota_exceeded
		datetime captured_at
	}

	UserActivityHistory {
		bigint user_activity_history_id PK 
		bigint source_event_id FK 
		varchar sentiance_user_id
		varchar activity_type
		datetime captured_at
	}

	TechnicalEventHistory {
		bigint technical_event_history_id PK 
		bigint source_event_id FK 
		varchar sentiance_user_id
		varchar technical_event_type
		text message
		text payload_json
		datetime captured_at
	}

	Trip {
		bigint trip_id PK 
		varchar sentiance_user_id
		varchar canonical_transport_event_id
		varchar first_seen_from
		varchar transport_mode
		datetime start_time
		bigint start_time_epoch
		datetime last_update_time
		bigint last_update_time_epoch
		datetime end_time
		bigint end_time_epoch
		numeric duration_in_seconds
		numeric distance_meters
		varchar occupant_role
		boolean is_provisional
		text transport_tags_json
		text waypoints_json
		datetime created_at
		datetime updated_at
	}

	SentianceEventos||--o|SdkSourceEvent:"deriva en"
	SdkSourceEvent||--o{SdkStatusHistory:"genera"
	SdkSourceEvent||--o{UserContextHeader:"genera"
	SdkSourceEvent||--o{DrivingInsightsTrip:"genera"
	SdkSourceEvent||--o{VehicleCrashEvent:"genera"
	SdkSourceEvent||--o{TimelineEventHistory:"genera"
	SdkSourceEvent||--o{TechnicalEventHistory:"genera"
	UserContextHeader||--o{UserContextEventDetail:"contiene"
	UserContextHeader||--o{UserContextActiveSegmentDetail:"contiene"
	UserContextHeader||--o{UserHomeHistory:"contiene"
	UserContextHeader||--o{UserWorkHistory:"contiene"
	UserContextHeader||--o{UserContextUpdateCriteria:"contiene"
	UserContextHeader||--o{UserActivityHistory:"genera"
	UserContextActiveSegmentDetail||--o{UserContextSegmentAttribute:"posee"
	DrivingInsightsTrip||--o{DrivingInsightsPhoneEvent:"registra"
	DrivingInsightsTrip||--o{DrivingInsightsSpeedingEvent:"registra"
	DrivingInsightsTrip||--o{DrivingInsightsHarshEvent:"registra"
	DrivingInsightsTrip||--o{DrivingInsightsCallEvent:"registra"
	DrivingInsightsTrip||--o{DrivingInsightsWrongWayDrivingEvent:"registra"
	Trip||--o{DrivingInsightsTrip:"es el ancestro de"
	TimelineEventHistory}o--||Trip:"alimenta a"
	UserContextEventDetail}o--||Trip:"alimenta a"
```

---

## 3. Diccionario de Datos (Mapeo por Tabla)

> A continuación, se detalla campo por campo cada tabla presente en el diagrama, vinculándola con la variable equivalente dictada por la documentación oficial de Sentiance react-native.

### 3.1. Tablas Base y Gestión

#### 3.1.1. `SentianceEventos`
Tabla originaria donde el backend "aterriza" la recepción del payload de la app móvil (Listener raw).

| Campo | Tipo | Mapeo Sentiance | 
| :--- | :--- | :--- | 
| `id` | INT (PK) | Auto-Generado Interno |
| `sentianceid` | VARCHAR | UUID del dispositivo extraído pre-procesamiento / Autenticación Custom |
| `fechahora` | DATETIME | Timestamp de inserción |
| `json` | TEXT | **Payload exacto emitido desde la app React Native**. |
| `tipo` | VARCHAR | Tipo de Listener (Ej. `UserContextUpdate`, `TimelineUpdate`, `DrivingInsightsReady`, `CrashEvent`) |
| `created_at` | DATETIME | Fecha/Hora Backend de escritura |
| `procesado` | BIT | Flag para ETL indicando si fue parseada a las tablas detalladas |
| `app_version`| VARCHAR | Custom Backend (versión de la App si se inyecta en headers HTTP/URL). |

#### 3.1.2. `SdkSourceEvent`
Auditoría de los registros. Permite referenciar un objeto normalizado a su JSON originario.

| Campo | Tipo | Mapeo Interno |
| :--- | :--- | :--- |
| `source_event_id` | BIGINT PK | ID subrogado |
| `id` | INT FK | Referencia al `id` de `SentianceEventos` |
| `record_type` | VARCHAR | Denominación del payload extraído (`CrashEvent`, `UserContext`, etc.) |
| `sentiance_user_id`| VARCHAR | `user_id` |
| `source_time` | DATETIME | Obtenido de los epoch del evento principal en el JSON |
| `source_event_ref`| VARCHAR | ID de referencia directa (`event.id` o `transportEvent.id`) |
| `payload_hash` | VARCHAR | Hash MD5/SHA para determinar unicidad de JSONs procesados |
| `created_at` | DATETIME | Tiempo Interno de normalización |

---

### 3.2. Dominio de Módulo Temporal (Timeline Events)

#### 3.2.1. `TimelineEventHistory`
Eventos de línea de tiempo del listener `addTimelineUpdateListener`. 
*Ref SDK: `react-native/event-timeline/timeline/definitions (Event Interface)`*

| Campo | Tipo | Mapeo Sentiance | JSON Detail |
| :--- | :--- | :--- | :--- |
| `timeline_event_history_id`| BIGINT PK | N/A | PK de tabla |
| `source_event_id` | BIGINT FK | N/A | Relación a `SdkSourceEvent` |
| `sentiance_user_id` | VARCHAR | N/A | ID Sentiance |
| `event_id` | VARCHAR | `id` | Id único del evento temporal |
| `event_type` | VARCHAR | `type` | *"STATIONARY", "OFF_THE_GRID", "IN_TRANSPORT"* |
| `start_time` | DATETIME | `startTime` | ISO 8601 string |
| `start_time_epoch`| BIGINT | `startTimeEpoch` | UTC milisegundos |
| `last_update_time`| DATETIME | `lastUpdateTime` | ISO 8601 string |
| `last_update_time_epoch`| BIGINT | `lastUpdateTimeEpoch`| UTC milisegundos |
| `end_time` | DATETIME | `endTime` | ISO 8601 string |
| `end_time_epoch` | BIGINT | `endTimeEpoch` | UTC milisegundos |
| `duration_in_seconds` | NUMERIC | `durationInSeconds` | Nulo si no culminó |
| `is_provisional` | BOOLEAN | `isProvisional` | Determina si es `true` (en curso) o `false` (final) |
| `transport_mode` | VARCHAR | `transportMode` | *"CAR", "BICYCLE", "WALKING", "UNKNOWN"...* |
| `distance_meters` | NUMERIC | `distance` | Distancia del transporte en metros |
| `occupant_role` | VARCHAR | `occupantRole` | *"DRIVER", "PASSENGER", "UNAVAILABLE"* |
| `transport_tags_json`| TEXT | `transportTags` | String JSON del objeto Key-Value asignado. |
| `location_latitude` | DECIMAL | `location.latitude` | Presente sólo para `STATIONARY` |
| `location_longitude` | DECIMAL | `location.longitude` | Presente sólo para `STATIONARY` |
| `location_accuracy` | NUMERIC | `location.accuracy` | Precisión estacionaria (mts) |
| `venue_significance`| VARCHAR | `venue.significance` | *"HOME", "WORK", "POINT_OF_INTEREST"* |
| `venue_type` | VARCHAR | `venue.type` | *"SHOP_LONG", "OFFICE", "RESIDENTIAL"...* |
| `waypoints_json` | TEXT | `waypoints` | String JSON de objetos de `Waypoint` |

---

### 3.3. Dominio de Contexto de Usuario (User Context)

Derivados del Listener `addUserContextUpdateListener`. 
*Ref SDK: `react-native/user-context/definitions (UserContext)`*

#### 3.3.1. `UserContextHeader`
Contiene la base del objeto superior `UserContextUpdate`.

| Campo | Tipo | Mapeo Sentiance | Detalles |
| :--- | :--- | :--- | :--- |
| `user_context_payload_id`| BIGINT PK | N/A | PK Interno |
| `source_event_id` | BIGINT FK | N/A | PK SdkSourceEvent |
| `sentiance_user_id`| VARCHAR | N/A | ID Sentiance |
| `context_source_type`| VARCHAR | N/A | Ejemplo: `USER_CONTEXT_LISTENER` |
| `semantic_time` | VARCHAR | `userContext.semanticTime` | *"MORNING", "LATE_MORNING", "NIGHT"*, etc. |
| `last_known_latitude` | DECIMAL | `lastKnownLocation.latitude` | Coordenada Y |
| `last_known_longitude`| DECIMAL | `lastKnownLocation.longitude`| Coordenada X |
| `last_known_accuracy` | NUMERIC | `lastKnownLocation.accuracy`| Precisión |

#### 3.3.2. `UserContextUpdateCriteria`
Los motivos de actualización extraídos del arreglo `criteria[]`.

| Campo | Tipo | Mapeo Sentiance |
| :--- | :--- | :--- |
| `user_context_update_criteria_id`| BIGINT PK| Auto |
| `user_context_payload_id` | BIGINT FK| FK Padre |
| `criteria_code` | VARCHAR | Elementos en `criteria`: *"CURRENT_EVENT"*, *"ACTIVE_SEGMENTS"*, *"VISITED_VENUES"* |

#### 3.3.3. `UserContextEventDetail`
Itera los eventos activos `events[]` actuales del contexto. 
Mapeo idéntico a `TimelineEventHistory` porque ambos usan el modelo `Event` (contiene `transportMode`, `occupantRole`, locations y demás). Única diferencia: Clave Foránea a `UserContextHeader`.

#### 3.3.4. `UserContextActiveSegmentDetail`
Desgloce de la lista `activeSegments[]` del usuario (Comportamientos/Segmentos inferidos).

| Campo | Tipo | Mapeo Sentiance |
| :--- | :--- | :--- |
| `user_context_segment_history_id`| BIGINT PK| ID Interno |
| `user_context_payload_id` | BIGINT FK | FK Padre |
| `sentiance_user_id`| VARCHAR | ID Sentiance |
| `segment_id` | VARCHAR | `id` (Identificador del Segmento) |
| `category` | VARCHAR | `category` (*"LEISURE", "MOBILITY", "WORK_LIFE"*) |
| `subcategory`| VARCHAR | `subcategory` (*"SHOPPING", "SOCIAL", "TRANSPORT"*) |
| `segment_type`| VARCHAR | `type` (*"CITY_WORKER", "EARLY_BIRD", "RESTO_LOVER"*) |
| `start_time` / `start_time_epoch` | DATETIME / BIGINT | `startTime` / `startTimeEpoch` |
| `end_time` / `end_time_epoch` | DATETIME / BIGINT | `endTime` / `endTimeEpoch` |

#### 3.3.5. `UserContextSegmentAttribute`
Iterado mediante objeto secundario `attributes[]` hijo del arreglo `activeSegments[]`.

| Campo | Tipo | Mapeo Sentiance |
| :--- | :--- | :--- |
| `attribute_name` | VARCHAR | `name` (Nombre del atributo en BD) |
| `attribute_value` | NUMERIC | `value` (Valor del atributo) |

#### 3.3.6. `UserHomeHistory` y `UserWorkHistory`
Lugares frecuentes estables `home` y `work` del `UserContext`.

| Campo | Tipo | Mapeo Sentiance |
| :--- | :--- | :--- |
| `user_home_history_id` (o work)| BIGINT PK| - | 
| `significance` | VARCHAR | `significance` ("HOME" / "WORK") |
| `venue_type` | VARCHAR | `type` ("RESIDENTIAL", "OFFICE"...) |
| `latitude`, `longitude`, `accuracy` | DECIMAL | En iterado `location` del venue |

---

### 3.4. Dominio de Hábitos Conductuales de Manejo (Driving Insights)

Vienen del listener `addDrivingInsightsReadyListener`, gatillado en transportes finalizados. Deben incluir a través de la app todas las llamadas auxiliares (`getHarshDrivingEvents`, `getCallEvents` etc.) encoladas en el JSON enviado al backend.
*Ref SDK: `react-native/driving-insights/definitions`*

#### 3.4.1. `DrivingInsightsTrip`
Mapeo principal de `DrivingInsights` (contiene `transportEvent` y `safetyScores`).

| Campo | Tipo | Mapeo Sentiance | Notas |
| :--- | :--- | :--- | :--- |
| `driving_insights_trip_id`| BIGINT PK| - | - |
| `source_event_id` | BIGINT FK| - | - |
| `trip_id` | BIGINT FK| - | FK de la tabla canon `Trip` |
| `sentiance_user_id` | VARCHAR | - | Obtenido de JWT|ID App |
| `transport_event_id` | VARCHAR | `transportEvent.id` | La ID original de Trip del Timeline / Contexto |
| `smooth_score` | NUMERIC | `safetyScores.smoothScore` | (0 a 1) |
| `focus_score` | NUMERIC | `safetyScores.focusScore` | (0 a 1) |
| `legal_score` | NUMERIC | `safetyScores.legalScore` | (0 a 1) |
| `call_while_moving_score`| NUMERIC | `safetyScores.callWhileMovingScore`| (0 a 1) |
| `overall_score` | NUMERIC | `safetyScores.overallScore`| (0 a 1) |
| `harsh_braking_score`| NUMERIC | `safetyScores.harshBrakingScore`| (0 a 1) |
| `harsh_turning_score`| NUMERIC | `safetyScores.harshTurningScore`| (0 a 1) |
| `harsh_acceleration_score`|NUMERIC | `safetyScores.harshAccelerationScore`| (0 a 1) |
| `wrong_way_driving_score`| NUMERIC | `safetyScores.wrongWayDrivingScore`| (0 a 1) |
| `attention_score`| NUMERIC | `safetyScores.attentionScore`| (0 a 1) |
| `distance_meters`| NUMERIC | `transportEvent.distance` | Distancia extraída en metros |
| `waypoints_json` | TEXT | `transportEvent.waypoints` | Serializado JSON global |

#### 3.4.2. `DrivingInsightsHarshEvent`
Deriva de `getHarshDrivingEvents()`.

| Campo | Tipo | Mapeo Sentiance (`HarshDrivingEvent[]`) |
| :--- | :--- | :--- |
| `start_time` / `epoch` | DATETIME/BIGINT| `startTime` / `startTimeEpoch` |
| `end_time` / `epoch` | DATETIME/BIGINT| `endTime` / `endTimeEpoch` |
| `magnitude` | NUMERIC | `magnitude` |
| `confidence` | NUMERIC | `confidence` |
| `harsh_type` | VARCHAR | `type` (*"ACCELERATION", "BRAKING", "TURN"*) |
| `waypoints_json`| TEXT | `waypoints[]` stringificado |

#### 3.4.3. `DrivingInsightsPhoneEvent` y `DrivingInsightsCallEvent`
Deriva de inyecciones de `getPhoneUsageEvents()` y `getCallEvents()`.

| Campo | Tipo | Mapeo Sentiance | Objeto Origen |
| :--- | :--- | :--- | :--- |
| `start_time` / `epoch` | DATETIME/BIGINT| `startTime` / `startTimeEpoch` | En ambos |
| `end_time` / `epoch` | DATETIME/BIGINT| `endTime` / `endTimeEpoch` | En ambos |
| `call_state` | VARCHAR | `callState` (*"NO_CALL"*, *"CALL_IN_PROGRESS"*) | Exclusivo de **PhoneEvent** |
| `min_traveled_speed_mps`| NUMERIC | `minTraveledSpeedInMps` | Exclusivo de **CallEvent** |
| `max_traveled_speed_mps`| NUMERIC | `maxTraveledSpeedInMps` | Exclusivo de **CallEvent** |
| `hands_free_state` | VARCHAR | `handsFreeState` (*"HANDS_FREE"*, *"HANDHELD"*) | Exclusivo de **CallEvent** |
| `waypoints_json` | TEXT | `waypoints[]` stringificado | En ambos |

#### 3.4.4. `DrivingInsightsSpeedingEvent` / `DrivingInsightsWrongWayDrivingEvent`
Análogos derivados de `getSpeedingEvents()` y `getWrongWayDrivingEvents()`.
Mapeo idéntico de base (`startTime`, `endTime`, `waypoints`).

---

### 3.5. Excepciones Vehiculares y Estado

#### 3.5.1. `VehicleCrashEvent`
Provisto a través de `addVehicleCrashEventListener`.
*Ref SDK: `react-native/crash-detection/definitions`*

| Campo | Tipo | Mapeo Sentiance (`CrashEvent`) |
| :--- | :--- | :--- |
| `vehicle_crash_event_id` | BIGINT PK | - |
| `crash_time_epoch` | BIGINT | `time` |
| `latitude`, `longitude`, `accuracy`, `altitude`| DECIMAL | Mapeado individual desde el objeto interno `location` al registrarse el impacto |
| `magnitude` | NUMERIC | `magnitude` |
| `speed_at_impact`| NUMERIC | `speedAtImpact` |
| `delta_v` | NUMERIC | `deltaV` (cambio de velocidad en km/h o mph) |
| `confidence` | NUMERIC | `confidence` |
| `severity` | VARCHAR | `severity` (*"LOW", "MEDIUM", "HIGH"*) |
| `detector_mode` | VARCHAR | `detectorMode` (*"CAR", "TWO_WHEELER"*) |

#### 3.5.2. `SdkStatusHistory`
Estado general de recolección en los dispositivos a través de status update listeners.

| Campo | Tipo | Base Teórica |
| :--- | :--- | :--- |
| `location_permission` | VARCHAR | Si los permisos Android/iOS correspondientes están garantizados |
| `precise_location_granted`| BOOLEAN | Permisos granulares |
| `detection_status` | VARCHAR | Porción operativa del SDK |
| `is_quota_exceeded`| BOOLEAN | Límite API / Offload |

#### 3.5.3. `UserActivityHistory` y `TechnicalEventHistory`
Logs técnicos de actividad o errores.

| Campo | Tipo | Detalles |
| :--- | :--- | :--- |
| `activity_type` | VARCHAR | Resumen ligero de actividad (Ej. *"TRIP", "STATIONARY"*) |
| `technical_event_type`| VARCHAR | Categoría Log de error / advertencia SDK |
| `message` | TEXT | Detalle del error |
| `payload_json` | TEXT | Trace de Error/Dump |

---

### 3.6. Tabla Integrada / Pivot ("Canon")

#### 3.6.1. `Trip`
**Importantísimo**: No es directamente poblada por un listener JSON Sentiance unitario, sino un integrador de viajes (Transports).

| Campo | Mapeo Backend a normalizar |
| :--- | :--- |
| `canonical_transport_event_id`| ID único originario (`event.id` / `transportEvent.id`) para sincronizar DrivingInsights con Timelines |
| `first_seen_from` | *"TIMELINE" | "USER_CONTEXT" | "DRIVING_INSIGHTS"* (La fuente desde donde el sistema del servidor vio el ID por primera vez) |
| `transport_mode`, `start_time` | Mapeado iterando si surge de Timeline, UserContextEvent, o Insight. |
| `duration_in_seconds`, `distance_meters`| Consolidados al finalizar (`endTime` no nulo) |
| `is_provisional`| Crucial para controlar el versionado del viaje: indica si el viaje aún puede modificarse y mutar (por Sentiance SDK) |
| `waypoints_json`| Si no se ha emitido en el DrivingInsight (ej. patines, trenes), se usa el `waypoints` del transportEvent base |

---

## 4. Anexo: Estructuras JSON Esperadas (Payloads SDK Mails)

Según la documentación oficial de Sentiance (React Native), las estructuras de los objetos clave emitidos por los listeners hacia el backend siguen la forma descrita a continuación. Esto es material de referencia para que el equipo backend sepa cómo extraer o deserializar cada propiedad.

### 4.1. Payload Listener: Timeline (`Event`)
*Estructura base usada tanto en el Timeline como en el detalle de eventos del User Context.*

```json
{
  "id": "e_xxxxxxxxxxx",
  "startTime": "2023-10-25T08:30:00.000Z",
  "startTimeEpoch": 1698222600000,
  "lastUpdateTime": "2023-10-25T08:45:00.000Z",
  "lastUpdateTimeEpoch": 1698223500000,
  "endTime": "2023-10-25T08:50:00.000Z",
  "endTimeEpoch": 1698223800000,
  "durationInSeconds": 1200,
  "type": "IN_TRANSPORT",
  "isProvisional": false,
  
  "transportMode": "CAR",
  "distance": 8500,
  "occupantRole": "DRIVER",
  "transportTags": {
     "my_custom_tag": "value"
  },
  
  "location": {
    "latitude": -34.603722,
    "longitude": -58.381592,
    "accuracy": 15
  },
  
  "venue": {
    "location": {
       "latitude": -34.603722,
       "longitude": -58.381592,
       "accuracy": 15
    },
    "significance": "WORK",
    "type": "OFFICE"
  },
  
  "waypoints": [
    {
      "latitude": -34.603722,
      "longitude": -58.381592,
      "accuracy": 10,
      "timestamp": 1698222605000,
      "speedLimitInMps": 16.66,
      "isSpeedLimitEstimated": false,
      "isSynthesized": true
    }
  ]
}
```
*(Nota: `location` y `venue` están típicamente presentes si `type == "STATIONARY"`, mientras que `waypoints`, `distance`, `occupantRole` y `transportMode` están si es `"IN_TRANSPORT"`).*


### 4.2. Payload Listener: User Context (`UserContext`)

```json
{
  "events": [
    { /* Array de objetos tipados como Timeline Event (Ver 4.1) */ }
  ],
  "activeSegments": [
    {
      "category": "WORK_LIFE",
      "subcategory": "WORK",
      "type": "CITY_WORKER",
      "id": "s_cityworker1",
      "startTime": "2023-10-01T00:00:00.000Z",
      "startTimeEpoch": 1696118400000,
      "endTime": null,
      "endTimeEpoch": null,
      "attributes": [
        {
          "name": "COMMUTE_DISTANCE",
          "value": 15.5
        }
      ]
    }
  ],
  "lastKnownLocation": {
    "latitude": -34.603722,
    "longitude": -58.381592,
    "accuracy": 20.5
  },
  "home": {
    "location": { "latitude": -34.5, "longitude": -58.4, "accuracy": 50 },
    "significance": "HOME",
    "type": "RESIDENTIAL"
  },
  "work": {
    "location": { "latitude": -34.6, "longitude": -58.3, "accuracy": 30 },
    "significance": "WORK",
    "type": "OFFICE"
  },
  "semanticTime": "MORNING"
}
```

### 4.3. Payload Listener: Driving Insights (`DrivingInsights`)
*Recibido cuando termina de procesarse por completo un viaje motorizado.*

```json
{
  "transportEvent": {
      /* Estructura Idéntica a Event 4.1 con type: IN_TRANSPORT */
      "id": "e_transport_123",
      "distance": 12500,
      "waypoints": [ ... ]
  },
  "safetyScores": {
    "smoothScore": 0.85,
    "focusScore": 0.90,
    "legalScore": 1.0,
    "callWhileMovingScore": 1.0,
    "overallScore": 0.89,
    "harshBrakingScore": 0.80,
    "harshTurningScore": 0.95,
    "harshAccelerationScore": 0.85,
    "wrongWayDrivingScore": 1.0,
    "attentionScore": 0.91
  }
}
```

### 4.4. Payloads Independientes: Sub-Eventos de Manejo (Harsh Events, Phone Events, etc.)

> **Nota importante:** La aplicación Front-End envía de forma **independiente** al backend los reportes de eventos derivados (no van empaquetados obligatoriamente dentro del objeto general de `DrivingInsights`). Cuando el backend reciba el JSON correspondiente a las llamadas de `getHarshDrivingEvents()`, `getPhoneUsageEvents()` o afines, percibirá un Array de objetos con el formato pertinente:

**Ejemplo de Payload JSON para Harsh Events (`HarshDrivingEvent[]`):**
```json
[
  {
    "startTime": "2023-10-25T08:35:00.000Z",
    "startTimeEpoch": 1698222900000,
    "endTime": "2023-10-25T08:35:03.000Z",
    "endTimeEpoch": 1698222903000,
    "magnitude": 4.5,
    "confidence": 0.98,
    "type": "BRAKING",
    "waypoints": [ { "latitude": -34.6, "longitude": -58.4, "timestamp": 1698222901000 } ]
  }
]
```

**Ejemplo de Payload JSON para Eventos Telefónicos (`CallEvent[]`):**
```json
[
  {
    "startTime": "2023-10-25T08:40:00.000Z",
    "startTimeEpoch": 1698223200000,
    "endTime": "2023-10-25T08:42:00.000Z",
    "endTimeEpoch": 1698223320000,
    "minTraveledSpeedInMps": 10.5,
    "maxTraveledSpeedInMps": 22.3,
    "handsFreeState": "HANDS_FREE",
    "waypoints": [ ... ]
  }
]
```

### 4.5. Payload Listener: Crash Detection (`CrashEvent`)

```json
{
  "time": 1698224000000,
  "location": {
    "latitude": -34.611111,
    "longitude": -58.377777,
    "accuracy": 5,
    "altitude": 14.5
  },
  "precedingLocations": [
    { /* Array de GeoLocation previos al choque */ }
  ],
  "magnitude": 8.5,
  "speedAtImpact": 45.5,
  "deltaV": 18.2,
  "confidence": 0.95,
  "severity": "HIGH",
  "detectorMode": "CAR"
}
```