# Diseño de Base de Datos - Eventos Sentiance

> **Versión:** 1.0.0  
> **Última Actualización:** 30 de marzo de 2026  
> **Motor Objetivo:** Microsoft SQL Server (T-SQL)

## 1. Contexto y Origen de Datos (Payloads)

Este modelo de base de datos está diseñado para almacenar estructuradamente la información recolectada por el **SDK de Sentiance** en aplicaciones móviles.

La información ingresa al backend mediante **eventos recibidos a través de los *listeners* del SDK en el dispositivo móvil** (en nuestro caso, bajo la implementación de React Native). 

**Puntos Importantes:**

- **Solo Listeners:** No se consolida información proveniente de los volcados diarios (Offloads). El stream es un pipeline directo donde la app móvil emite el payload JSON directamente al backend.
- **Formato Crudo (Raw):** El JSON almacenado inicialmente en la tabla `SentianceEventos` es el payload exacto emitido por el SDK, sin agregados, sobres ni modificaciones de parte del backend.  Si bien la idea es comprimir el mensaje antes de enviarlo, mi propuesta es guardarlo descompactado y legible por humanos para facilitar el debugging. El presente esquema propuesto permite purgar periódicamente esta tabla de modo que no hay peligro de un crecimiento descontrolado de la necesidad de almacenamiento.
- **Múltiples Fuentes de Viajes (`Trip`):** La entidad central `Trip` (viaje) no proviene de un solo payload. Es una tabla normalizada alimentada por múltiples fuentes: Eventos temporales (`TimelineEvent` o del `UserContext`) especialmente útiles para viajes cortos, peatonales, bicicletas o colectivos, y objetos de `DrivingInsights` para trayectos motorizados de autos/motos.

---

## 2. Diagrama Entidad-Relación (ER)

```mermaid
erDiagram
	direction TB
	SentianceEventos {
		int id PK 
		varchar sentianceid
		nvarchar(max) json
		varchar tipo
		datetime created_at
		bit is_processed
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
		bit is_provisional
		varchar transport_mode
		numeric distance_meters
		varchar occupant_role
		nvarchar(max) transport_tags_json
		decimal location_latitude
		decimal location_longitude
		numeric location_accuracy
		varchar venue_significance
		varchar venue_type
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
		bit is_provisional
		varchar transport_mode
		numeric distance_meters
		varchar occupant_role
		nvarchar(max) transport_tags_json
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
		numeric distance_meters
		varchar occupant_role
		nvarchar(max) transport_tags_json
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
		nvarchar(max) waypoints_json
	}

	DrivingInsightsPhoneEvent {
		bigint phone_event_id PK 
		bigint source_event_id FK 
		bigint driving_insights_trip_id FK 
		datetime start_time
		bigint start_time_epoch
		datetime end_time
		bigint end_time_epoch
		nvarchar(max) waypoints_json
	}

	DrivingInsightsCallEvent {
		bigint call_event_id PK 
		bigint source_event_id FK 
		bigint driving_insights_trip_id FK 
		datetime start_time
		bigint start_time_epoch
		datetime end_time
		bigint end_time_epoch
		numeric min_travelled_speed_mps
		numeric max_travelled_speed_mps
		nvarchar(max) waypoints_json
	}

	DrivingInsightsSpeedingEvent {
		bigint speeding_event_id PK 
		bigint source_event_id FK 
		bigint driving_insights_trip_id FK 
		datetime start_time
		bigint start_time_epoch
		datetime end_time
		bigint end_time_epoch
		nvarchar(max) waypoints_json
	}

	DrivingInsightsWrongWayDrivingEvent {
		bigint wrong_way_event_id PK 
		bigint source_event_id FK 
		bigint driving_insights_trip_id FK 
		datetime start_time
		bigint start_time_epoch
		datetime end_time
		bigint end_time_epoch
		nvarchar(max) waypoints_json
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
		nvarchar(max) preceding_locations_json
	}

	SdkStatusHistory {
		bigint sdk_status_history_id PK 
		bigint source_event_id FK 
		varchar sentiance_user_id
		varchar start_status
		varchar detection_status
		varchar location_permission
		bit precise_location_granted
		varchar quota_status_wifi
		varchar quota_status_mobile
		varchar quota_status_disk
		bit is_location_available
		bit can_detect
		datetime captured_at
	}

	UserActivityHistory {
		bigint user_activity_history_id PK 
		bigint source_event_id FK 
		varchar sentiance_user_id
		varchar activity_type
		varchar trip_type
		decimal stationary_latitude
		decimal stationary_longitude
		nvarchar(max) payload_json
		datetime captured_at
	}

	TechnicalEventHistory {
		bigint technical_event_history_id PK 
		bigint source_event_id FK 
		varchar sentiance_user_id
		varchar technical_event_type
		nvarchar(max) message
		nvarchar(max) payload_json
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
		bit is_provisional
		nvarchar(max) transport_tags_json
		nvarchar(max) waypoints_json
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
	SdkSourceEvent||--o{UserActivityHistory:"genera"
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

> **📍 MOTOR OBJETIVO: Microsoft SQL Server (T-SQL)**  
> Todo el esquema ER y el Diccionario de Datos están pensados estructuralmente para ser implementados en **Microsoft SQL Server**.
> - Campos booleanos lógicos se expresan como `BIT` (`0` / `1`).
> - Objetos anidados en JSON y strings extensos (sin longitud predecible) se tipan como `NVARCHAR(MAX)`. En el caso de los waypoints podría valer la pena guardarolos en algún formato más compacto tipo CBOR ya que es altamente improbable que debamos hacer búsquedas por valores dentro de ese campo.
> - Columnas numéricas usan `NUMERIC`, `DECIMAL` o `BIGINT` en lugar de literales genéricos para garantizar exactitud temporal y espacial.

> A continuación, se detalla campo por campo cada tabla presente en el diagrama, vinculándola con la variable equivalente dictada por la documentación  de Sentiance react-native.

### 3.1. Tablas Base y Gestión

#### 3.1.1. `SentianceEventos`

Tabla originaria donde el backend "aterriza" la recepción del payload de la app móvil (Listener raw).


| Campo          | Tipo          | Mapeo Sentiance                                                                                                                                                              |
| -------------- | ------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `id`           | INT (PK)      | Auto-Generado Interno                                                                                                                                                        |
| `sentianceid`  | VARCHAR       | Identificador del usuario.                                                                                                                                                   |
| `json`         | NVARCHAR(MAX) | **Payload exacto emitido desde la app React Native**.                                                                                                                        |
| `tipo`         | VARCHAR       | Tipo de Listener (Ej. `UserContextUpdate`, `TimelineUpdate`, `DrivingInsightsReady`, `CrashEvent`)                                                                           |
| `created_at`   | DATETIME      | Marca de tiempo asignada por el servidor backend de forma local al instante de recepcionar el webhook HTTP (ej. `GETDATE()`)                                                 |
| `is_processed` | BIT           | Flag nativo de control de este pipeline ETL (Extract -> Transform -> Load): seteado a `1` una vez el JSON fue parseado y distribuido exitosamente a las tablas normalizadas. |
| `procesado`    | BIT           | **⚠️ LEGACY / EXTERNO:** Flag preexistente manipulado por rutinas ajenas a esta integración. No tiene relación alguna con este pipeline documental. **Ignorar**.             |
| `app_version`  | VARCHAR       | Custom Backend (versión de la App si se inyecta en headers HTTP/URL).                                                                                                        |


#### 3.1.2. `SdkSourceEvent`

Auditoría de los registros. Permite referenciar un objeto normalizado a su JSON originario.


| Campo               | Tipo      | Mapeo Interno                                                         |
| ------------------- | --------- | --------------------------------------------------------------------- |
| `source_event_id`   | BIGINT PK | Clave única autogenerada                                              |
| `id`                | INT FK    | Referencia al `id` de `SentianceEventos`                              |
| `record_type`       | VARCHAR   | Denominación del payload extraído (`CrashEvent`, `UserContext`, etc.) |
| `sentiance_user_id` | VARCHAR   | `user_id`                                                             |
| `source_time`       | DATETIME  | Obtenido de los epoch del evento principal en el JSON                 |
| `source_event_ref`  | VARCHAR   | ID de referencia directa (`event.id` o `transportEvent.id`)           |
| `payload_hash`      | VARCHAR   | Hash MD5/SHA para determinar unicidad de JSONs procesados             |
| `created_at`        | DATETIME  | Tiempo Interno de normalización                                       |


**Nota**: tal vez convendría guardar la fecha también en formato legible por 

humanos

### 3.2. Dominio de Módulo Temporal (Timeline Events)

#### 3.2.1. `TimelineEventHistory`

Eventos de línea de tiempo del listener `addTimelineUpdateListener`.  
*Ref SDK: `react-native/event-timeline/timeline/definitions (Event Interface)*`


| Campo                       | Tipo          | Mapeo Sentiance       | JSON Detail                                                                                                                                                             |
| --------------------------- | ------------- | --------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `timeline_event_history_id` | BIGINT PK     | N/A                   | PK de tabla                                                                                                                                                             |
| `source_event_id`           | BIGINT FK     | N/A                   | Relación a `SdkSourceEvent`                                                                                                                                             |
| `sentiance_user_id`         | VARCHAR       | N/A                   | ID Sentiance                                                                                                                                                            |
| `event_id`                  | VARCHAR       | `id`                  | Id único del evento temporal. **Nota:** Si `event_type` es *"IN_TRANSPORT"*, este ID coincide exactamente con el `canonical_transport_event_id` de la tabla `**Trip**`. |
| `event_type`                | VARCHAR       | `type`                | Enum estricto: *"UNKNOWN", "STATIONARY", "OFF_THE_GRID", "IN_TRANSPORT"*                                                                                                |
| `start_time`                | DATETIME      | `startTime`           | ISO 8601 string                                                                                                                                                         |
| `start_time_epoch`          | BIGINT        | `startTimeEpoch`      | UTC milisegundos                                                                                                                                                        |
| `last_update_time`          | DATETIME      | `lastUpdateTime`      | ISO 8601 string                                                                                                                                                         |
| `last_update_time_epoch`    | BIGINT        | `lastUpdateTimeEpoch` | UTC milisegundos                                                                                                                                                        |
| `end_time`                  | DATETIME      | `endTime`             | ISO 8601 string                                                                                                                                                         |
| `end_time_epoch`            | BIGINT        | `endTimeEpoch`        | UTC milisegundos                                                                                                                                                        |
| `duration_in_seconds`       | NUMERIC       | `durationInSeconds`   | Nulo si no culminó                                                                                                                                                      |
| `is_provisional`            | BIT           | `isProvisional`       | Determina si es `true` (en curso) o `false` (final)                                                                                                                     |
| `transport_mode`            | VARCHAR       | `transportMode`       | Enum estricto: *"UNKNOWN", "BICYCLE", "WALKING", "RUNNING", "TRAM", "TRAIN", "CAR", "BUS", "MOTORCYCLE"*                                                                |
| `distance_meters`           | NUMERIC       | `distance`            | Distancia del transporte en metros                                                                                                                                      |
| `occupant_role`             | VARCHAR       | `occupantRole`        | *"DRIVER", "PASSENGER", "UNAVAILABLE"*                                                                                                                                  |
| `transport_tags_json`       | NVARCHAR(MAX) | `transportTags`       | String JSON del objeto Key-Value asignado.                                                                                                                              |
| `location_latitude`         | DECIMAL       | `location.latitude`   | Presente sólo para `STATIONARY`                                                                                                                                         |
| `location_longitude`        | DECIMAL       | `location.longitude`  | Presente sólo para `STATIONARY`                                                                                                                                         |
| `location_accuracy`         | NUMERIC       | `location.accuracy`   | Precisión estacionaria (mts)                                                                                                                                            |
| `venue_significance`        | VARCHAR       | `venue.significance`  | Enum estricto: *"UNKNOWN", "HOME", "WORK", "POINT_OF_INTEREST"*                                                                                                         |
| `venue_type`                | VARCHAR       | `venue.type`          | Enum extenso con docenas de categorías (incluye *"UNKNOWN"*, *"SHOP_LONG"*, *"OFFICE"*, *"RESIDENTIAL"*, etc.)                                                          |


---

### 3.3. Dominio de Contexto de Usuario (User Context)

Derivados del Listener `addUserContextUpdateListener`.  
*Ref SDK: `react-native/user-context/definitions (UserContext)*`

#### 3.3.1. `UserContextHeader`

Contiene los datos básicos del objeto `UserContextUpdate` y sirve como punto de entrada para los segmentos y eventos que vienen en el mismo lote.

**Relación con Tablas Dependientes**:  
Para recuperar los datos asociados a una actualización, usa el `**source_event_id**` (Foreign Key):

- En `**UserContextSegmentHistory**` estarán los segmentos de este lote.
- En `**UserTimelineEventHistory**` estarán los eventos de este lote.

**Política de Inserción (UPSERT)**:  
Para evitar registros repetidos en el historial si un mismo evento llega en distintas actualizaciones:

1. **Eventos**: No duplicar si el `**event_id**` (Sentiance) ya existe.
2. **Segmentos**: No duplicar si el par `**(sentiance_user_id, segment_id)**` ya existe.


| Campo                     | Tipo      | Mapeo Sentiance               | Detalles                                                                                                                                 |
| ------------------------- | --------- | ----------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| `user_context_payload_id` | BIGINT PK | N/A                           | Identificador único e incremental para cada registro de contexto recibido, sirviendo como raíz para las tablas de criterios y segmentos. |
| `source_event_id`         | BIGINT FK | N/A                           | PK SdkSourceEvent                                                                                                                        |
| `sentiance_user_id`       | VARCHAR   | N/A                           | ID Sentiance                                                                                                                             |
| `context_source_type`     | VARCHAR   | N/A                           | Ejemplo: `USER_CONTEXT_LISTENER`                                                                                                         |
| `semantic_time`           | VARCHAR   | `userContext.semanticTime`    | *"MORNING", "LATE_MORNING", "NIGHT"*, etc.                                                                                               |
| `last_known_latitude`     | DECIMAL   | `lastKnownLocation.latitude`  | Coordenada Y                                                                                                                             |
| `last_known_longitude`    | DECIMAL   | `lastKnownLocation.longitude` | Coordenada X                                                                                                                             |
| `last_known_accuracy`     | NUMERIC   | `lastKnownLocation.accuracy`  | Precisión                                                                                                                                |


#### 3.3.2. `UserContextUpdateCriteria`

Los motivos de actualización extraídos del arreglo `criteria[]`.


| Campo                             | Tipo      | Mapeo Sentiance                                                                                                                                                                                                                                                                                               |
| --------------------------------- | --------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `user_context_update_criteria_id` | BIGINT PK | Auto                                                                                                                                                                                                                                                                                                          |
| `user_context_payload_id`         | BIGINT FK | FK referenciando a `UserContextHeader(user_context_payload_id)`.                                                                                                                                                                                                                                              |
| `criteria_code`                   | VARCHAR   | Indica el motivo de la actualización. Un `UserContextUpdate` puede tener múltiples motivos simultáneos (ej. cambió el evento y se actualizaron segmentos), por lo que se debe insertar un registro por cada elemento del array recibido. Valores: *"CURRENT_EVENT"*, *"ACTIVE_SEGMENTS"*, *"VISITED_VENUES"*. |


#### 3.3.3. `UserContextEventDetail`

Itera los eventos activos `events[]` actuales del contexto.  
Mapeo idéntico a `TimelineEventHistory` porque ambos usan el modelo `Event` (contiene `transportMode`, `occupantRole`, locations y demás). Única diferencia: Clave Foránea a `UserContextHeader`.

> **⚠️ Nota de Normalización y Almacenamiento:** Aunque el objeto nativo extraído `events[]` contiene un voluminoso array de `waypoints` (coordenadas en milisegundos del trayecto), este campo fue **omitido intencionalmente** del esquema `UserContextEventDetail`. Para evitar duplicidad extrema de Megabytes en JSON, dichos recorridos se almacenan de manera única en la tabla pivote `**Trip**`.

#### 3.3.4. `UserContextActiveSegmentDetail`

Desgloce de la lista `activeSegments[]` del usuario (Comportamientos/Segmentos inferidos).


| Campo                             | Tipo              | Mapeo Sentiance                                                  |
| --------------------------------- | ----------------- | ---------------------------------------------------------------- |
| `user_context_segment_history_id` | BIGINT PK         | ID Interno                                                       |
| `user_context_payload_id`         | BIGINT FK         | FK referenciando a `UserContextHeader(user_context_payload_id)`. |
| `sentiance_user_id`               | VARCHAR           | ID Sentiance                                                     |
| `segment_id`                      | VARCHAR           | `id` (Identificador del Segmento)                                |
| `category`                        | VARCHAR           | `category` (*"LEISURE", "MOBILITY", "WORK_LIFE"*)                |
| `subcategory`                     | VARCHAR           | `subcategory` (*"SHOPPING", "SOCIAL", "TRANSPORT"*)              |
| `segment_type`                    | VARCHAR           | `type` (*"CITY_WORKER", "EARLY_BIRD", "RESTO_LOVER"*)            |
| `start_time` / `start_time_epoch` | DATETIME / BIGINT | `startTime` / `startTimeEpoch`                                   |
| `end_time` / `end_time_epoch`     | DATETIME / BIGINT | `endTime` / `endTimeEpoch`                                       |


#### 3.3.5. `UserContextSegmentAttribute`

Iterado mediante objeto secundario `attributes[]` hijo del arreglo `activeSegments[]`.


| Campo                             | Tipo      | Mapeo Sentiance                                                                  |
| --------------------------------- | --------- | -------------------------------------------------------------------------------- |
| `user_context_segment_attr_id`    | BIGINT PK | Auto                                                                             |
| `user_context_segment_history_id` | BIGINT FK | FK referenciando a `UserContextSegmentHistory(user_context_segment_history_id)`. |
| `attribute_name`                  | VARCHAR   | `name` (Nombre del atributo)                                                     |
| `attribute_value`                 | NUMERIC   | `value` (Valor del atributo)                                                     |


#### 3.3.6. `UserHomeHistory` y `UserWorkHistory`

Lugares frecuentes estables `home` y `work` del `UserContext`.


| Campo                           | Tipo      | Mapeo Sentiance                                                  |
| ------------------------------- | --------- | ---------------------------------------------------------------- |
| `user_home_history_id` (o work) | BIGINT PK | Auto                                                             |
| `user_context_payload_id`       | BIGINT FK | FK referenciando a `UserContextHeader(user_context_payload_id)`. |
| `significance`                  | VARCHAR   | `significance` (*"HOME" / "WORK"*)                               |
| `venue_type`                    | VARCHAR   | `type` (*"RESIDENTIAL", "OFFICE"*)                               |
| `latitude`                      | DECIMAL   | `location.latitude`                                              |
| `longitude`                     | DECIMAL   | `location.longitude`                                             |
| `accuracy`                      | NUMERIC   | `location.accuracy`                                              |


---

### 3.4. Dominio de Hábitos Conductuales de Manejo (Driving Insights)

Vienen del listener `addDrivingInsightsReadyListener`, gatillado en transportes finalizados. Deben incluir a través de la app todas las llamadas auxiliares (`getHarshDrivingEvents`, `getCallWhileMovingEvents` etc.) encoladas en el JSON enviado al backend.  
*Ref SDK: `react-native/driving-insights/definitions*`

#### 3.4.1. `DrivingInsightsTrip`

Mapeo principal de `DrivingInsights` (contiene `transportEvent` y `safetyScores`).

> **⚠️ Nota de Normalización (Omisión de Waypoints):** A pesar de que el objeto nativo extraído `transportEvent` contiene un array pesado de `waypoints` (tracking geoespacial a milisegundos), esta propiedad fue **purgada intencionalmente** del mapeo DDL de `DrivingInsightsTrip`. Para eficientizar el almacenamiento y evitar gigabytes de coordenadas duplicadas, el guardado de `waypoints_json` de todos los viajes se delega de forma exclusiva y consolidada a la tabla canónica central `**Trip**`.


| Campo                      | Tipo          | Mapeo Sentiance                       | Notas                                                     |
| -------------------------- | ------------- | ------------------------------------- | --------------------------------------------------------- |
| `driving_insights_trip_id` | BIGINT PK     | -                                     | -                                                         |
| `source_event_id`          | BIGINT FK     | -                                     | FK referenciando a `SdkSourceEvent(source_event_id)`.     |
| `trip_id`                  | BIGINT FK     | -                                     | FK referenciando a la tabla canónica `Trip(trip_id)`.     |
| `sentiance_user_id`        | VARCHAR       | -                                     | Sentiance Id                                              |
| `transport_event_id`       | VARCHAR       | `transportEvent.id`                   | La ID original de Trip del Timeline / Contexto            |
| `smooth_score`             | NUMERIC       | `safetyScores.smoothScore`            | (0 a 1)                                                   |
| `focus_score`              | NUMERIC       | `safetyScores.focusScore`             | (0 a 1)                                                   |
| `legal_score`              | NUMERIC       | `safetyScores.legalScore`             | (0 a 1)                                                   |
| `call_while_moving_score`  | NUMERIC       | `safetyScores.callWhileMovingScore`   | (0 a 1)                                                   |
| `overall_score`            | NUMERIC       | `safetyScores.overallScore`           | (0 a 1)                                                   |
| `harsh_braking_score`      | NUMERIC       | `safetyScores.harshBrakingScore`      | (0 a 1)                                                   |
| `harsh_turning_score`      | NUMERIC       | `safetyScores.harshTurningScore`      | (0 a 1)                                                   |
| `harsh_acceleration_score` | NUMERIC       | `safetyScores.harshAccelerationScore` | (0 a 1)                                                   |
| `distance_meters`          | NUMERIC       | `transportEvent.distance`             | Distancia extraída en metros                              |
| `occupant_role`            | VARCHAR       | `transportEvent.occupantRole`         | Enum estricto: *"DRIVER"*, *"PASSENGER"*, *"UNAVAILABLE"* |
| `transport_tags_json`      | NVARCHAR(MAX) | `transportEvent.transportTags`        | Serializado dict key-value                                |


#### 3.4.2. `DrivingInsightsHarshEvent`

Deriva de `getHarshDrivingEvents()`.


| Campo                      | Tipo          | Mapeo Sentiance                              | Notas                                                                      |
| -------------------------- | ------------- | -------------------------------------------- | -------------------------------------------------------------------------- |
| `harsh_event_id`           | BIGINT PK     | Auto                                         | Identificador único del evento brusco.                                     |
| `source_event_id`          | BIGINT FK     | FK Raíz                                      | FK referenciando a `SdkSourceEvent(source_event_id)`.                      |
| `driving_insights_trip_id` | BIGINT FK     | FK Padre                                     | FK referenciando a `DrivingInsightsTrip(driving_insights_trip_id)`.        |
| `start_time`               | DATETIME      | `startTime`                                  | Inicio del evento.                                                         |
| `start_time_epoch`         | BIGINT        | `startTimeEpoch`                             | Tiempo Unix de inicio.                                                     |
| `end_time`                 | DATETIME      | `endTime`                                    | Fin del evento.                                                            |
| `end_time_epoch`           | BIGINT        | `endTimeEpoch`                               | Tiempo Unix de fin.                                                        |
| `magnitude`                | NUMERIC       | `magnitude`                                  | Fuerza G máxima detectada.                                                 |
| `confidence`               | NUMERIC       | `confidence`                                 | Nivel de confianza (0-1).                                                  |
| `harsh_type`               | VARCHAR       | `type` (*"ACCELERATION", "BRAKING", "TURN"*) | Tipo de evento brusco.                                                     |
| `waypoints_json`           | NVARCHAR(MAX) | `waypoints[]`                                | Array completo de puntos del evento (Lat/Long/Alt) en formato JSON string. |


#### 3.4.3. `DrivingInsightsCallEvent`

Deriva de llamadas auxiliares a `getPhoneUsageEvents()` y `getCallWhileMovingEvents()`.

> **💡 Nota de Nomenclatura (Frontend vs Backend):** Oficialmente, en el contrato y documentación TypeScript de Sentiance, los objetos de llamadas mientras se maneja están empaquetados bajo la interfaz `CallWhileMovingEvent`. En esta Base de Datos se denominó explícitamente a la tabla como `**DrivingInsightsCallEvent**` por mera consistencia de diseño para estandarizar todos los "insights" vehiculares. Por lo tanto: `**CallWhileMovingEvent` ≡ `DrivingInsightsCallEvent**`.


| Campo                      | Tipo          | Mapeo Sentiance        | Notas                                                               |
| -------------------------- | ------------- | ---------------------- | ------------------------------------------------------------------- |
| `call_event_id`            | BIGINT PK     | Auto                   | Identificador único del evento de llamada.                          |
| `source_event_id`          | BIGINT FK     | FK Raíz                | FK referenciando a `SdkSourceEvent(source_event_id)`.               |
| `driving_insights_trip_id` | BIGINT FK     | FK Padre               | FK referenciando a `DrivingInsightsTrip(driving_insights_trip_id)`. |
| `start_time`               | DATETIME      | `startTime`            | Inicio de la llamada.                                               |
| `start_time_epoch`         | BIGINT        | `startTimeEpoch`       | Tiempo Unix de inicio.                                              |
| `end_time`                 | DATETIME      | `endTime`              | Fin de la llamada.                                                  |
| `end_time_epoch`           | BIGINT        | `endTimeEpoch`         | Tiempo Unix de fin.                                                 |
| `min_travelled_speed_mps`  | NUMERIC       | `minTravelledSpeedMps` | Velocidad mínima durante la llamada (metros por segundo).           |
| `max_travelled_speed_mps`  | NUMERIC       | `maxTravelledSpeedMps` | Velocidad máxima durante la llamada (metros por segundo).           |
| `waypoints_json`           | NVARCHAR(MAX) | `waypoints[]`          | Array de puntos del evento (Lat/Long/Alt) en formato JSON string.   |


#### 3.4.4. `DrivingInsightsSpeedingEvent`

Deriva de `getSpeedingEvents()`.


| Campo                      | Tipo          | Mapeo Sentiance  | Notas                                                               |
| -------------------------- | ------------- | ---------------- | ------------------------------------------------------------------- |
| `speeding_event_id`        | BIGINT PK     | Auto             | Identificador único del evento de exceso de velocidad.              |
| `source_event_id`          | BIGINT FK     | FK Raíz          | FK referenciando a `SdkSourceEvent(source_event_id)`.               |
| `driving_insights_trip_id` | BIGINT FK     | FK Padre         | FK referenciando a `DrivingInsightsTrip(driving_insights_trip_id)`. |
| `start_time`               | DATETIME      | `startTime`      | Inicio del exceso de velocidad.                                     |
| `start_time_epoch`         | BIGINT        | `startTimeEpoch` | Tiempo Unix de inicio.                                              |
| `end_time`                 | DATETIME      | `endTime`        | Fin del exceso de velocidad.                                        |
| `end_time_epoch`           | BIGINT        | `endTimeEpoch`   | Tiempo Unix de fin.                                                 |
| `waypoints_json`           | NVARCHAR(MAX) | `waypoints[]`    | Array de puntos del evento (Lat/Long/Alt) en formato JSON string.   |


#### 3.4.5. `DrivingInsightsWrongWayDrivingEvent`

Deriva de `getWrongWayDrivingEvents()`.


| Campo                      | Tipo          | Mapeo Sentiance  | Notas                                                               |
| -------------------------- | ------------- | ---------------- | ------------------------------------------------------------------- |
| `wrong_way_event_id`       | BIGINT PK     | Auto             | Identificador único del evento de conducción en contramano.         |
| `source_event_id`          | BIGINT FK     | FK Raíz          | FK referenciando a `SdkSourceEvent(source_event_id)`.               |
| `driving_insights_trip_id` | BIGINT FK     | FK Padre         | FK referenciando a `DrivingInsightsTrip(driving_insights_trip_id)`. |
| `start_time`               | DATETIME      | `startTime`      | Inicio de la conducción en contramano.                              |
| `start_time_epoch`         | BIGINT        | `startTimeEpoch` | Tiempo Unix de inicio.                                              |
| `end_time`                 | DATETIME      | `endTime`        | Fin de la conducción en contramano.                                 |
| `end_time_epoch`           | BIGINT        | `endTimeEpoch`   | Tiempo Unix de fin.                                                 |
| `waypoints_json`           | NVARCHAR(MAX) | `waypoints[]`    | Array de puntos del evento (Lat/Long/Alt) en formato JSON string.   |


#### 3.4.6. `DrivingInsightsPhoneEvent`

Deriva de `getPhoneUsageEvents()`. Representa los momentos en que el conductor interactúa con el teléfono móvil durante el trayecto.

| Campo                      | Tipo          | Mapeo Sentiance  | Notas                                                               |
| -------------------------- | ------------- | ---------------- | ------------------------------------------------------------------- |
| `phone_event_id`           | BIGINT PK     | Auto             | Identificador único del evento de distracción.                      |
| `source_event_id`          | BIGINT FK     | FK Raíz          | FK referenciando a `SdkSourceEvent(source_event_id)`.               |
| `driving_insights_trip_id` | BIGINT FK     | FK Padre         | FK referenciando a `DrivingInsightsTrip(driving_insights_trip_id)`. |
| `start_time`               | DATETIME      | `startTime`      | Inicio del uso del teléfono.                                        |
| `start_time_epoch`         | BIGINT        | `startTimeEpoch` | Tiempo Unix de inicio.                                              |
| `end_time`                 | DATETIME      | `endTime`        | Fin del uso del teléfono.                                           |
| `end_time_epoch`           | BIGINT        | `endTimeEpoch`   | Tiempo Unix de fin.                                                 |
| `waypoints_json`           | NVARCHAR(MAX) | `waypoints[]`    | Array de puntos del evento (Lat/Long/Alt) en formato JSON string.   |

---

### 3.5. Excepciones Vehiculares y Estado

#### 3.5.1. `VehicleCrashEvent`

Provisto a través de `addVehicleCrashEventListener`.  
*Ref SDK: `react-native/crash-detection/definitions*`


| Campo                      | Tipo          | Mapeo Sentiance                                   | Notas                                                 |
| -------------------------- | ------------- | ------------------------------------------------- | ----------------------------------------------------- |
| `vehicle_crash_event_id`   | BIGINT PK     | Auto                                              | Identificador único del evento de choque.             |
| `source_event_id`          | BIGINT FK     | FK Raíz                                           | FK referenciando a `SdkSourceEvent(source_event_id)`. |
| `sentiance_user_id`        | VARCHAR       | -                                                 | ID del usuario de Sentiance.                          |
| `crash_time_epoch`         | BIGINT        | `time`                                            | Tiempo Unix del impacto.                              |
| `latitude`                 | DECIMAL       | `location.latitude`                               | Coordenada Y del impacto.                             |
| `longitude`                | DECIMAL       | `location.longitude`                              | Coordenada X del impacto.                             |
| `accuracy`                 | NUMERIC       | `location.accuracy`                               | Precisión del GPS al momento del impacto.             |
| `altitude`                 | NUMERIC       | `location.altitude`                               | Altitud al momento del impacto.                       |
| `magnitude`                | NUMERIC       | `magnitude`                                       | Magnitud del choque.                                  |
| `speed_at_impact`          | NUMERIC       | `speedAtImpact`                                   | Velocidad al momento del impacto.                     |
| `delta_v`                  | NUMERIC       | `deltaV`                                          | Cambio de velocidad inducido por el impacto.          |
| `confidence`               | NUMERIC       | `confidence`                                      | Nivel de confianza del sensor (0-1).                  |
| `severity`                 | VARCHAR       | `severity`                                        | Gravedad (*"LOW", "MEDIUM", "HIGH"*).                 |
| `detector_mode`            | VARCHAR       | `detectorMode` (*"CAR", "TWO_WHEELER"*)           |                                                       |
| `preceding_locations_json` | NVARCHAR(MAX) | Stringificado del JSON Array `precedingLocations` |                                                       |


#### 3.5.2. `SdkStatusHistory`

Estado general de recolección en los dispositivos a través del listener de status updates. Mapeado desde el payload nativo `SdkStatus`.

> **⚠️ Nota de Captura Parcial (Muestreo Intencional):** La interfaz original TypeScript `SdkStatus` expone numeramente docenas de propiedades y banderas técnicas (tales como `userExists`, `backgroundRefreshStatus`, `isRemoteEnabled`, `isBatteryOptimizationEnabled`, `isAirplaneModeEnabled`, etc.). El modelo de base de datos optó por registrar de forma controlada estrictamente un subset de sus atributos, priorizando aquellos vinculados al cuote de tracking y localización ("is_location_available", "location_permission", etc., que componen la tabla relacional) para así mitigar la saturación de ruido técnico y maximizar el rendimiento DB. Por ende, la abstracción tabular en `SdkStatusHistory` se trata de un filtrado parcial e intencional, y no de un Mapeo Estructural 1:1 directo de todos los flag del SDK Status original.


| Campo                      | Tipo      | Mapeo Sentiance y Detalles                            | Notas                             |
| -------------------------- | --------- | ----------------------------------------------------- | --------------------------------- |
| `sdk_status_history_id`    | BIGINT PK | Auto                                                  | -                                 |
| `source_event_id`          | BIGINT FK | FK referenciando a `SdkSourceEvent(source_event_id)`. | -                                 |
| `sentiance_user_id`        | VARCHAR   | Identificador del usuario.                            | -                                 |
| `start_status`             | VARCHAR   | `startStatus`                                         | Estado de arranque del SDK.       |
| `detection_status`         | VARCHAR   | `detectionStatus`                                     | Estado operativo de detección.    |
| `location_permission`      | VARCHAR   | `locationPermission`                                  | Permisos del sistema operativo.   |
| `precise_location_granted` | BIT       | `isPreciseLocationGranted`                            | Si se tiene precisión GPS total.  |
| `quota_status_wifi`        | VARCHAR   | `quotaStatusWiFi`                                     | Estado de cuota en WiFi.          |
| `quota_status_mobile`      | VARCHAR   | `quotaStatusMobile`                                   | Estado de cuota en datos móviles. |
| `quota_status_disk`        | VARCHAR   | `quotaStatusDisk`                                     | Estado de cuota en disco.         |
| `is_location_available`    | BIT       | `isLocationAvailable`                                 | Si la ubicación está encendida.   |
| `can_detect`               | BIT       | `canDetect`                                           | Si el SDK puede recolectar datos. |
| `captured_at`              | DATETIME  | Instante de persistencia del status.                  | -                                 |
| `precise_location_granted` | BIT       | Extraído de `isPreciseLocationAuthorizationGranted`.  |                                   |
| `quota_status_wifi`        | VARCHAR   | Extraído de `wifiQuotaStatus`.                        |                                   |
| `quota_status_mobile`      | VARCHAR   | Extraído de `mobileQuotaStatus`.                      |                                   |
| `quota_status_disk`        | VARCHAR   | Extraído de `diskQuotaStatus`.                        |                                   |
| `is_location_available`    | BIT       | Extraído de `isLocationAvailable`.                    |                                   |
| `can_detect`               | BIT       | Extraído de `canDetect`.                              |                                   |


#### 3.5.3. `UserActivityHistory`

Recopilación de contextos gruesos emitidos por el listener de User Activity. Mapeado del payload nativo `UserActivity`.


| Campo                      | Tipo          | Mapeo Sentiance y Detalles                                                   | Notas |
| -------------------------- | ------------- | ---------------------------------------------------------------------------- | ----- |
| `user_activity_history_id` | BIGINT PK     | Auto                                                                         | -     |
| `source_event_id`          | BIGINT FK     | FK referenciando a `SdkSourceEvent(source_event_id)`.                        | -     |
| `sentiance_user_id`        | VARCHAR       | Identificador del usuario.                                                   | -     |
| `activity_type`            | VARCHAR       | `type` (Ej. *"USER_ACTIVITY_TYPE_TRIP"*, *"USER_ACTIVITY_TYPE_STATIONARY"*). | -     |
| `trip_type`                | VARCHAR       | `tripInfo.type`. Solo si la actividad es de tipo viaje.                      | -     |
| `stationary_latitude`      | DECIMAL       | `stationaryInfo.location.latitude`. **⚠️ Permite NULL** si no hay señal.     | -     |
| `stationary_longitude`     | DECIMAL       | `stationaryInfo.location.longitude`. **⚠️ Permite NULL** si no hay señal.    | -     |
| `payload_json`             | NVARCHAR(MAX) | Copia raw del JSON `UserActivity`.                                           | -     |
| `captured_at`              | DATETIME      | Instante de persistencia de la actividad.                                    | -     |


#### 3.5.4. `TechnicalEventHistory`

Logueo de advertencias o errores nativos del SDK, para debugging en servidor sin depender del volcado Offload (Payload sujeto a implementación de logger).


| Campo                        | Tipo          | Mapeo Sentiance y Detalles                                        | Notas |
| ---------------------------- | ------------- | ----------------------------------------------------------------- | ----- |
| `technical_event_history_id` | BIGINT PK     | Auto                                                              | -     |
| `source_event_id`            | BIGINT FK     | FK referenciando a `SdkSourceEvent(source_event_id)`.             | -     |
| `sentiance_user_id`          | VARCHAR       | Identificador del usuario.                                        | -     |
| `technical_event_type`       | VARCHAR       | Tipo de evento técnico (ej: *"ERROR"*, *"WARNING"*, *"SDK_LOG"*). | -     |
| `message`                    | NVARCHAR(MAX) | Descripción textual del evento o error.                           | -     |
| `payload_json`               | NVARCHAR(MAX) | Contenido crudo del log técnico para análisis profundo.           | -     |
| `captured_at`                | DATETIME      | Instante de persistencia del evento.                              | -     |


---

### 3.6. Tabla Integrada / Pivot ("Canon")

#### 3.6.1. `Trip`

**Importantísimo**: No es directamente poblada por un listener JSON Sentiance unitario, sino un integrador de viajes (Transports).


| Campo                          | Tipo          | Mapeo Sentiance       | Notas                                                                         |
| ------------------------------ | ------------- | --------------------- | ----------------------------------------------------------------------------- |
| `trip_id`                      | BIGINT PK     | Auto                  | Identificador único del viaje (consolidado).                                  |
| `sentiance_user_id`            | VARCHAR       | -                     | ID del usuario de Sentiance.                                                  |
| `canonical_transport_event_id` | VARCHAR       | `id` (del transporte) | ID original de Sentiance para de-duplicación global.                          |
| `first_seen_from`              | VARCHAR       | -                     | Origen del primer registro (*"TIMELINE"*, *"CONTEXT"*, *"DRIVING_INSIGHTS"*). |
| `transport_mode`               | VARCHAR       | `transportMode`       | Modo de transporte (CAR, BUS, WALKING, etc.).                                 |
| `start_time`                   | DATETIME      | `startTime`           | Inicio global del viaje.                                                      |
| `start_time_epoch`             | BIGINT        | `startTimeEpoch`      | Tiempo Unix de inicio.                                                        |
| `last_update_time`             | DATETIME      | `lastUpdateTime`      | Fecha de la última actualización reportada por el SDK.                        |
| `last_update_time_epoch`       | BIGINT        | `lastUpdateTimeEpoch` | Tiempo Unix de la última actualización.                                       |
| `end_time`                     | DATETIME      | `endTime`             | Fin global del viaje (si ha finalizado).                                      |
| `end_time_epoch`               | BIGINT        | `endTimeEpoch`        | Tiempo Unix de fin.                                                           |
| `duration_in_seconds`          | NUMERIC       | `durationInSeconds`   | Duración total calculada en segundos.                                         |
| `distance_meters`              | NUMERIC       | `distanceInMeters`    | Distancia total recorrida en metros.                                          |
| `occupant_role`                | VARCHAR       | `occupantRole`        | Rol del ocupante (*"DRIVER"*, *"PASSENGER"*).                                 |
| `is_provisional`               | BIT           | `isProvisional`       | Flag para distinguir borradores de viajes finales definitivos.                |
| `transport_tags_json`          | NVARCHAR(MAX) | `transportTags`       | Tags adicionales del transporte en formato JSON.                              |
| `waypoints_json`               | NVARCHAR(MAX) | `waypoints[]`         | **Punto Único de Verdad**: Coordenadas consolidadas del viaje.                |
| `created_at`                   | DATETIME      | Auto                  | Fecha de creación técnica del registro.                                       |
| `updated_at`                   | DATETIME      | Auto                  | Fecha de última actualización técnica del registro.                           |


> **IMPORTANTE: Cómo trata el backend a los eventos provisionales y finales (`isProvisional`)**:  
> Según la documentación de Sentiance, los eventos provisionales generados en tiempo real **se generan independientemente a los finales y NO tienen el mismo ID**. 
> - A medida que el usuario se mueve, el SDK genera eventos provisorios en tiempo real (ej: "En movimiento IN_TRANSPORT") donde `isProvisional` es `true`. Estos se iteran e insertan en la tabla `Trip` como historias/segmentos. 
> - Una vez que el usuario se vuelve a quedar estacionario, Sentiance consolida todo el movimiento previo, procesa los scores y emite los eventos **Finales** (`isProvisional = false`). Los eventos finales tienen **IDs completamente nuevos** y Sentiance no provee links/claves foráneas apuntando a sus eventos "borrador" preliminares.
> - *↳ **Resultado en Base de Datos**: El backend **no actualiza ni reemplaza (UPDATE)** los records provisionales. Simplemente ingresa la nueva fila definitiva enviada por el evento final. Para análisis de scores de viaje limpio, reporting, o consumo en la UI usuaria final, la base de datos se debe filtrar buscando excluyentemente `WHERE is_provisional = 0` para aislar el output definitivo del viaje, descartando los borradores en tiempo real.*

> [!NOTE]
> **Nota Técnica de Implementación: Deduplicación vs Desvinculación de Viajes**  
> Es imperativo para el equipo de Backend (ETL) distinguir mecánicamente entre dos flujos totalmente diferentes al procesar identificadores (`canonical_transport_event_id`):
> 1. **Deduplicación de Evento Final (Uso de UPDATE / MERGE):** Cuando un "Viaje Final" concluye, múltiples módulos nativos de Sentiance (`UserContext`, `DrivingInsights`, `Timeline`) se disparan concurrentemente hacia la nube. Todos emiten de manera redundante el **mismo ID de viaje Final**. El backend debe usar `MERGE` en T-SQL para que el webhook que llegue primero realice el `INSERT` original, y los webhooks subsecuentes (que traen el mismo ID) realicen un `UPDATE`, enriqueciendo la fila única (ej. anexándole `waypoints` y Safety Scores).
> 2. **Desvinculación absoluta del Provisorio (Uso exclusivo de INSERT):** Los eventos en vivo emitidos en tiempo real (donde `isProvisional = true`) usan un ID propio que **no guarda relación alguna u originaria** con el ID del evento Final. El `MERGE` del webhook final nunca va a "coincidir" ni pisar al borrador. Cada evento provisorio que expulse la App simplemente realiza un `INSERT` pasivo (se acumulan muertos), y cuando se despacha el Viaje Final definitivo meses o minutos después, se somete a un `INSERT` independiente en otra fila con un GUID completamente nuevo.

---

## 3.7. Índices de Base de Datos Recomendados (Alto Volumen)

Debido a que una plataforma telemática conectada a múltiples dispositivos móviles (especialmente si recopila datos a baja latencia en ~1Hz o al detectar movimiento) genera cientos de miles o millones de filas rápidamente, la definición del DDL debe incluir índices **B-Tree** precisos para no deteriorar los tiempos de las consultas del negocio.

Por el diseño establecido, recomendamos enfáticamente crear los siguientes índices sobre las tablas de alto impacto (`SentianceEventos`, `TimelineEventHistory`, `UserActivityHistory` y `Trip`):

1. **Índice sobre `sentiance_user_id**` (Alta Cardinalidad):
  Casi cualquier pantalla principal del sistema (ej: "Consultar viajes del usuario X") o el filtrado por conductor usa esta columna. Al crear un index (ej: `idx_user_context_sentiance_user_id`) se evitan búsquedas Full-Table Scan que demorarían minutos.
2. **Índice sobre Timestamp (`start_time`, `start_time_epoch` o `captured_at`)** (Rangos Continuos):
  Crítico para análisis de flotas ("Viajes creados este mes") o para depuración de payloads antiguos. La combinación de un índice compuesto multicolumna `(sentiance_user_id, start_time_epoch)` cubrirá el 99% de las consultas analíticas del Dashboard.
3. **Índice Filtrado por `is_provisional`:**
  Tablas como `Trip` o `TimelineEventHistory` frecuentemente serán consultadas bajo la estricta premisa `WHERE is_provisional = 0`. Generar un índice condicional (particularmente un *Filtered Index* en SQL Server: `CREATE INDEX idx_final_trips ON Trip (trip_id) WHERE is_provisional = 0`) hará que listar la billetera de viajes finalizados sea instantáneo sin escanear el remanente inútil temporal.
4. **Índices en Claves Foráneas (`trip_id`, `source_event_id`)**:
  Siempre construir explícitamente índices sobre las FK `trip_id` en las subtablas dependientes (como `DrivingInsightsPhoneEvent` o `DrivingInsightsTrip`). Si se requiere investigar frenadas bruscas durante un bloque de viaje particular, la Join entre `Trip` y la tabla satélite dependerá de que el motor SQL encuentre rápidamente dicha sub-lista de FKs.
5. **Índice Único Transaccional (UNIQUE CONSTRAINT)**:
  En la tabla colaborativa maestra `Trip`, es **fundamental** indexar `canonical_transport_event_id` bajo una restricción única (`UNIQUE INDEX / CONSTRAINT`). Sin ella, el mecanismo atómico de `UPSERT` ("si existe hago update, sino insert") no es viable y generará carreras críticas.

---

## 4. Anexo: Estructuras JSON Esperadas (Payloads SDK Principales)

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
      "speedInMps": 12.5,
      "speedLimitInMps": 16.66,
      "isSpeedLimitInfoSet": true,
      "hasUnlimitedSpeedLimit": false,
      "isSynthetic": true
    }
  ]
}
```

*(Nota: `location` y `venue` están típicamente presentes si `type == "STATIONARY"`, mientras que `waypoints`, `distance`, `occupantRole` y `transportMode` están si es `"IN_TRANSPORT"`).*

### 4.2. Payload Listener: User Context (`UserContext`)

```json
{
  "criteria": [
    "CURRENT_EVENT",
    "ACTIVE_SEGMENTS"
  ],
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
    "harshAccelerationScore": 0.85
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
    "minTravelledSpeedInMps": 10.5,
    "maxTravelledSpeedInMps": 22.3,
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

### 4.6. Anexo de Definiciones TypeScript (Referencia SDK React Native)

A continuación se adjuntan, a modo de complemento, las interfaces oficiales y nativas en *TypeScript* que documenta el módulo `@sentiance-react-native/driving-insights`. Este es el contrato real de datos con el que contarán los programadores del Front-End para generar el JSON Final:

```typescript
export interface DrivingInsights {  
  transportEvent: TransportEvent;
  safetyScores: SafetyScores;
}

export interface SafetyScores {  
  smoothScore?: number;
  focusScore?: number;
  legalScore?: number;
  callWhileMovingScore?: number;
  overallScore?: number;
  harshBrakingScore?: number;
  harshTurningScore?: number;
  harshAccelerationScore?: number;
}

export interface DrivingEvent {  
  startTime: string;  
  startTimeEpoch: number; // in milliseconds  
  endTime: string;  
  endTimeEpoch: number; // in milliseconds  
  waypoints: Waypoint[];  
}

export type HarshDrivingEventType = "ACCELERATION" | "BRAKING" | "TURN";

export interface HarshDrivingEvent extends DrivingEvent {  
  magnitude: number;  
  confidence: number;  
  type: HarshDrivingEventType;  
}

export interface PhoneUsageEvent extends DrivingEvent {}

export interface CallWhileMovingEvent extends DrivingEvent {  
  maxTravelledSpeedInMps?: number;  
  minTravelledSpeedInMps?: number;  
}

export interface SpeedingEvent extends DrivingEvent {}

// Hereda todos los campos de DrivingEvent sin agregar propiedades estructurales adicionales
export interface WrongWayDrivingEvent extends DrivingEvent {}

export interface TransportEvent {  
  id: string;  
  startTime: string;  
  startTimeEpoch: number; // in milliseconds  
  lastUpdateTime: string;  
  lastUpdateTimeEpoch: number; // in milliseconds  
  endTime: string | null;  
  endTimeEpoch: number | null; // in milliseconds  
  durationInSeconds: number | null;  
  type: string;  
  transportMode: TransportMode | null;  
  waypoints: Waypoint[];  
  distance?: number; // in meters  
  transportTags: TransportTags;  
  occupantRole: OccupantRole;  
  isProvisional: boolean;  
}

export type TransportTags = { [key: string]: string };
export type TransportMode = "UNKNOWN" | "BICYCLE" | "WALKING" | "RUNNING" | "TRAM" | "TRAIN" | "CAR" | "BUS" | "MOTORCYCLE";
export type OccupantRole = "DRIVER" | "PASSENGER" | "UNAVAILABLE";

export interface Waypoint {  
  latitude: number;  
  longitude: number;  
  accuracy: number;   // in meters  
  timestamp: number;  // UTC epoch time in milliseconds  
  speedInMps?: number;  // in meters per second  
  speedLimitInMps?: number;  // in meters per second  
  hasUnlimitedSpeedLimit: boolean;  
  isSpeedLimitInfoSet: boolean;  
  isSynthetic: boolean;  
}

export interface SdkStatus {
  startStatus: string;
  detectionStatus: string;
  canDetect: boolean;
  isRemoteEnabled: boolean;
  isAccelPresent: boolean;
  isGyroPresent: boolean;
  isGpsPresent: boolean;
  wifiQuotaStatus: string;
  mobileQuotaStatus: string;
  diskQuotaStatus: string;
  locationPermission: string;
  userExists: boolean;
  isBatterySavingEnabled?: boolean;
  isActivityRecognitionPermGranted?: boolean;
  isPreciseLocationAuthorizationGranted: boolean;
  isBgAccessPermGranted?: boolean; // iOS only
  locationSetting?: string; // Android only
  isAirplaneModeEnabled?: boolean; // Android only
  isLocationAvailable?: boolean;
  isGooglePlayServicesMissing?: boolean; // Android only
  isBatteryOptimizationEnabled?: boolean; // Android only
  isBackgroundProcessingRestricted?: boolean; // Android only
  isSchedulingExactAlarmsPermitted?: boolean; // Android only
  backgroundRefreshStatus: string; // iOS only
}

export interface Location {
  timestamp?: number; // marked optional to maintain compatibility, but is always present
  latitude: number;
  longitude: number;
  accuracy?: number;
  altitude?: number;
  provider?: string; // Android only
}

export interface StationaryInfo {
  location?: Location;
}

export interface TripInfo {
  type: "TRIP_TYPE_SDK" | "TRIP_TYPE_EXTERNAL" | "TRIP_TYPE_UNRECOGNIZED" | "ANY";
}

export interface UserActivity {
  type: "USER_ACTIVITY_TYPE_TRIP" | "USER_ACTIVITY_TYPE_STATIONARY" | "USER_ACTIVITY_TYPE_UNKNOWN" | "USER_ACTIVITY_TYPE_UNRECOGNIZED";
  tripInfo?: TripInfo;
  stationaryInfo?: StationaryInfo;
}
```

---

## 5. Anexo II: Flujo de Datos y Consolidación (Sequence Diagram)

El siguiente diagrama de secuencia ilustra de forma arquitectónica y cronológica cómo fluyen y se procesan los payloads emitidos por el SDK de Sentiance, desde su concepción por el lado móvil hasta su estructuración atómica normalizada final en el esquema de base de datos relacional previamente delineado.

```mermaid
sequenceDiagram
    autonumber
    participant App as App Móvil (SDK Sentiance)
    participant API as Endpoint Backend
    participant Raw as DB: SentianceEventos (Raw)
    participant ETL as Worker / ETL Parser
    participant Source as DB: SdkSourceEvent
    participant Trip as DB: Trip (Pivot)
    participant Satelite as DB: Tablas Satélites (Dependientes)

    note over App,API: Fase 1: Recolección y Volcado (Alta Velocidad)
    App->>API: POST /webhook (JSON Payload según Listener)
    activate API
    API->>Raw: INSERT (payload_json crudo, tipo)
    Raw-->>API: Retorna `evento_sentiance_id`
    API-->>App: HTTP 200 OK (Desacoplo del procesamiento)
    deactivate API

    note over ETL,Satelite: Fase 2: Procesamiento Asíncrono (ETL / Normalización)
    rect rgb(240, 248, 255)
        ETL->>Raw: SELECT Top(N) WHERE is_processed = 0
        activate ETL
        Raw-->>ETL: Lote de eventos encapsulados en JSON
        
        ETL->>ETL: Parser: Deserializa e identifica el Event Type
        
        ETL->>Source: INSERT SdkSourceEvent (Metadatos Generales)
        Source-->>ETL: Retorna `source_event_id` (Genera Raíz)
        
        opt Contiene Trayecto ("transportEvent" o "Event")
            ETL->>Trip: MERGE (T-SQL Upsert) sobre canonical_transport_event_id
            note right of Trip: Si no existe = INSERT (Inscribe Trip ID por 1ra vez).<br>Si existe = UPDATE (Deduplica el *Mismo Evento Final* emitido por diferentes webhooks concurrentes, NUNCA sobrescribe borradores).
            Trip-->>ETL: Retorna `trip_id`
        end
        
        ETL->>Satelite: INSERT Tablas Dependientes (DrivingInsightsPhone, TimelineHist, etc.)
        note right of Satelite: Anclados via FK (source_event_id) y ocasionalmente FK (trip_id)
        
        ETL->>Raw: UPDATE SentianceEventos (Marcado como is_processed = 1)
        deactivate ETL
    end
```

### 4.7. Anexo de Definiciones: User Context (Comportamiento y Segmentos)

Adicionalmente a las métricas de manejo, el SDK de Sentiance emite información sobre el contexto de vida del usuario a través del objeto `**UserContextUpdate**`. 

**Nota Técnica sobre el Modelado**:  
A diferencia de los eventos técnicos simples, el contexto de usuario es multidimensional (contiene una lista de segmentos activos, una lista de eventos recientes y lugares de interés como hogar/trabajo). Para evitar el almacenamiento de JSONs masivos y redundantes que degraden el rendimiento de las consultas, el sistema requiere la implementación de **Tablas Auxiliares** de normalización. 

Esto permite:

1. **Histórico de Segmentos**: Consultar la evolución de un usuario (ej. de "Early Bird" a "Night Owl") sin escanear payloads crudos.
2. **Deduplicación de Venues**: Almacenar una sola vez la coordenada de "Hogar" o "Trabajo" y relacionarla por IDs.
3. **Optimización de Búsqueda**: Filtrar rápidamente usuarios por `SegmentCategory` (ej. "MOBILITY") para campañas de marketing o análisis de riesgo.

A continuación se detallan las interfaces que componen el objeto raíz `**UserContextUpdate**`:

```typescript
declare module "@sentiance-react-native/user-context" {
  export interface UserContextUpdate {
    readonly criteria: ("CURRENT_EVENT" | "ACTIVE_SEGMENTS" | "VISITED_VENUES")[];
    readonly userContext: UserContext;
  }

  export type SegmentCategory = "LEISURE" | "MOBILITY" | "WORK_LIFE";
  
  export type SegmentSubcategory =
    | "COMMUTE" | "DRIVING" | "ENTERTAINMENT" | "FAMILY" | "HOME"
    | "SHOPPING" | "SOCIAL" | "TRANSPORT" | "TRAVEL" | "WELLBEING"
    | "WINING_AND_DINING" | "WORK";

  export type SegmentType =
    | "AGGRESSIVE_DRIVER" | "ANTICIPATIVE_DRIVER" | "BAR_GOER" | "CITY_DRIVER"
    | "CITY_HOME" | "CITY_WORKER" | "CULTURE_BUFF" | "DIE_HARD_DRIVER"
    | "DISTRACTED_DRIVER" | "DOG_WALKER" | "EARLY_BIRD" | "EASY_COMMUTER"
    | "EFFICIENT_DRIVER" | "FOODIE" | "FREQUENT_FLYER" | "FULLTIME_WORKER"
    | "GREEN_COMMUTER" | "HEALTHY_BIKER" | "HEALTHY_WALKER" | "HEAVY_COMMUTER"
    | "HOME_BOUND" | "HOMEBODY" | "HOMEWORKER" | "ILLEGAL_DRIVER"
    | "LATE_WORKER" | "LEGAL_DRIVER" | "LONG_COMMUTER" | "MOBILITY"
    | "MOTORWAY_DRIVER" | "MUSIC_LOVER" | "NATURE_LOVER" | "NIGHT_OWL"
    | "NIGHTWORKER" | "NORMAL_COMMUTER" | "PARTTIME_WORKER" | "PET_OWNER"
    | "PUBLIC_TRANSPORTS_USER" | "RECENTLY_CHANGED_JOB" | "RECENTLY_MOVED_HOME"
    | "RESTO_LOVER" | "RURAL_HOME" | "RURAL_WORKER" | "SHOPAHOLIC"
    | "SHORT_COMMUTER" | "SLEEP_DEPRIVED" | "SOCIAL_ACTIVITY"
    | "SPORTIVE" | "STUDENT" | "TOWN_HOME" | "TOWN_WORKER"
    | "UBER_PARENT" | "WORK_LIFE_BALANCE" | "WORK_TRAVELLER" | "WORKAHOLIC";

  export type VenueType =
    | "UNKNOWN" | "DRINK_DAY" | "DRINK_EVENING" | "EDUCATION_INDEPENDENT"
    | "EDUCATION_PARENTS" | "HEALTH" | "INDUSTRIAL" | "LEISURE_BEACH"
    | "LEISURE_DAY" | "LEISURE_EVENING" | "LEISURE_MUSEUM" | "LEISURE_NATURE"
    | "LEISURE_PARK" | "OFFICE" | "RELIGION" | "RESIDENTIAL" | "RESTO_MID"
    | "RESTO_SHORT" | "SHOP_LONG" | "SHOP_SHORT" | "SPORT" | "SPORT_ATTEND"
    | "TRAVEL_BUS" | "TRAVEL_CONFERENCE" | "TRAVEL_FILL" | "TRAVEL_HOTEL"
    | "TRAVEL_LONG" | "TRAVEL_SHORT";

  export interface UserContext {
    events: Event[];
    activeSegments: Segment[];
    lastKnownLocation: GeoLocation | null;
    home: Venue | null;
    work: Venue | null;
  }

  export interface Event {
    id: string;
    startTime: string;
    startTimeEpoch: number;
    lastUpdateTime: string;
    lastUpdateTimeEpoch: number;
    endTime: string | null;
    endTimeEpoch: number | null;
    durationInSeconds: number | null;
    type: "STATIONARY" | "IN_TRANSPORT" | "OFF_THE_GRID" | "UNKNOWN";
    isProvisional: boolean;
    // Contexto espacial
    location: GeoLocation | null;
    venue: Venue | null;
    // Contexto de transporte
    transportMode: string | null;
    waypoints: Waypoint[];
    distance?: number;
    occupantRole: "DRIVER" | "PASSENGER" | "UNAVAILABLE";
  }

  export interface GeoLocation {
    latitude: number;
    longitude: number;
    accuracy: number;
  }

  export interface Waypoint {
    latitude: number;
    longitude: number;
    accuracy: number;
    timestamp: number;
    speedInMps?: number;
    speedLimitInMps?: number;
    hasUnlimitedSpeedLimit: boolean;
    isSpeedLimitInfoSet: boolean;
    isSynthetic: boolean;
  }

  export interface Venue {
    location: GeoLocation | null;
    significance: "HOME" | "WORK" | "POINT_OF_INTEREST" | "UNKNOWN";
    type: VenueType;
  }

  export interface Segment {
    category: SegmentCategory;
    subcategory: SegmentSubcategory;
    type: SegmentType;
    id: number;
    startTime: string;
    startTimeEpoch: number;
    endTime: string | null;
    endTimeEpoch: number | null;
    attributes: SegmentAttribute[];
  }

  export interface SegmentAttribute {
    name: string;
    value: number;
  }

  export interface SentianceUserContext {
    requestUserContext(includeProvisionalEvents?: boolean): Promise<UserContext>;
    addUserContextUpdateListener(
      onUserContextUpdated: (userContextUpdate: UserContextUpdate) => void,
      includeProvisionalEvents?: boolean
    ): Promise<any>;
  }
}
```