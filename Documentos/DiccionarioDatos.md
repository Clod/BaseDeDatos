# Diccionario de Datos - Base de Datos VictaTMTK

Este documento contiene la descripción técnica detallada del esquema de base de datos relacional diseñado para la ingesta, normalización y análisis de telemetría móvil proveniente de la plataforma **Sentiance (Versión 2026)**.

---

## 🗂️ Índice de Tablas

### Etapa 1: Ingesta Cruda y Auditoría

1. [SentianceEventos](#1-sentianceeventos) - Zona de aterrizaje cruda (Landing Zone).
2. [SentianceEventos_Errors](#2-sentianceeventos_errors) - Logs de fallos de ingesta.
3. [SdkSourceEvent](#3-sdksourceevent) - Registro de procedencia normalizado.

### Etapa 2: Datos de Dominio y Perfil

1. [UserMetadata](#4-usermetadata) - Metadatos personalizados por usuario.
2. [Trip](#5-trip) - Entidad centralizada de transportes y viajes.

### Etapa 3: Seguridad y Driving Insights

1. [DrivingInsightsTrip](#6-drivinginsightstrip) - Puntuaciones de seguridad del viaje.
2. [DrivingInsightsHarshEvent](#7-drivinginsightsharshevent) - Maniobras bruscas (aceleración, frenado, giro).
3. [DrivingInsightsPhoneEvent](#8-drivinginsightsphoneevent) - Uso físico del teléfono al conducir.
4. [DrivingInsightsCallEvent](#9-drivinginsightscallevent) - Llamadas telefónicas en movimiento.
5. [DrivingInsightsSpeedingEvent](#10-drivinginsightsspeedingevent) - Intervalos de exceso de velocidad.
6. [DrivingInsightsWrongWayDrivingEvent](#11-drivinginsightswrongwaydrivingevent) - Conducción a contramano.

### Etapa 4: Contexto de Usuario y Localizaciones

1. [UserContextHeader](#12-usercontextheader) - Cabecera de cambios de contexto.
2. [UserContextUpdateCriteria](#13-usercontextupdatecriteria) - Criterios de actualización de contexto.
3. [UserHomeHistory](#14-userhomehistory) - Registro de venues clasificados como "Casa".
4. [UserWorkHistory](#15-userworkhistory) - Registro de venues clasificados como "Trabajo".
5. [UserContextActiveSegmentDetail](#16-usercontextactivesegmentdetail) - Segmentos de perfil activos del usuario.
6. [UserContextSegmentAttribute](#17-usercontextsegmentattribute) - Atributos numéricos de los segmentos.
7. [UserContextEventDetail](#18-usercontexteventdetail) - Historial detallado de eventos de contexto (`STATIONARY`, `IN_TRANSPORT`).

### Etapa 5: Históricos del SDK y Eventos Críticos

1. [TimelineEventHistory](#19-timelineeventhistory) - Historial unificado de la línea de tiempo del SDK.
2. [UserActivityHistory](#20-useractivityhistory) - Resúmenes simplificados de actividades (`TRIP`, `STATIONARY`).
3. [TechnicalEventHistory](#21-technicaleventhistory) - Logs técnicos, de soporte y de canalización.
4. [VehicleCrashEvent](#22-vehiclecrashevent) - Detección de colisiones/choques vehiculares graves.
5. [SdkStatusHistory](#23-sdkstatushistory) - Logs de estado del SDK y permisos móviles del usuario.

### Etapa 6: Multi-tenancy

1. [UserOrganization](#24-userorganization) - Mapeo usuario → organización cliente para filtrado multi-tenant.

---

## 🏗️ Detalles Técnicos por Tabla

### 1. SentianceEventos

Tabla de aterrizaje cruda donde se insertan los payloads JSON de eventos recibidos del SDK de Sentiance antes de cualquier normalización.

| Campo          | Tipo de Datos   | Claves / Nulabilidad  | Valor por Defecto | Descripción y Propósito Conceptual                                                                         |
| -------------- | --------------- | --------------------- | ----------------- | ---------------------------------------------------------------------------------------------------------- |
| `id`           | `BIGINT`        | PRIMARY KEY, NOT NULL | `IDENTITY(1,1)`   | Identificador único autoincremental del registro crudo.                                                    |
| `sentianceid`  | `VARCHAR(64)`   | NULL                  | *Ninguno*         | ID único del usuario generado por la API o plataforma de Sentiance.                                        |
| `json`         | `NVARCHAR(MAX)` | NULL                  | *Ninguno*         | Payload original del evento JSON completo en formato de texto.                                             |
| `tipo`         | `VARCHAR(32)`   | NULL                  | *Ninguno*         | Tipo de evento recibido (ej. `UserContextUpdate`, `DrivingInsights, DrivingInsightsSpeedingEvents, etc.`). |
| `created_at`   | `DATETIME2(3)`  | NULL                  | `GETDATE()`       | Marca de tiempo exacta en que se persistió el registro en la base de datos local.                          |
| `is_processed` | `BIT`           | NULL                  | `0`               | Flag técnico que indica si el procesamiento relacional de este evento finalizó.                            |
| `procesado`    | `BIT`           | NULL                  | `0`               | Flag secundario para compatibilidad de estados del pipeline de extracción (Legacy).                        |
| `app_version`  | `VARCHAR(32)`   | NULL                  | *Ninguno*         | Versión de la app cliente que transmitió el evento (extraída del header o payload).                        |

### 2. SentianceEventos_Errors

Almacena de forma persistente los eventos que generaron excepciones de parseo o de integridad al intentar ser procesados, facilitando tareas de diagnóstico técnico.

| Campo               | Tipo de Datos   | Claves / Nulabilidad  | Valor por Defecto | Descripción y Propósito Conceptual                                                   |
| ------------------- | --------------- | --------------------- | ----------------- | ------------------------------------------------------------------------------------ |
| `error_id`          | `BIGINT`        | PRIMARY KEY, NOT NULL | `IDENTITY(1,1)`   | Identificador único de registro de error.                                            |
| `original_id`       | `BIGINT`        | NOT NULL              | *Ninguno*         | Referencia al `id` de la tabla `SentianceEventos` que falló en procesarse.           |
| `sentiance_user_id` | `VARCHAR(64)`   | NULL                  | *Ninguno*         | ID del usuario de Sentiance relacionado con el fallo (si se pudo parsear).           |
| `tipo`              | `VARCHAR(32)`   | NULL                  | *Ninguno*         | Tipo del evento que falló.                                                           |
| `raw_json`          | `NVARCHAR(MAX)` | NULL                  | *Ninguno*         | Copia exacta del JSON crudo que causó la falla técnica.                              |
| `error_message`     | `NVARCHAR(MAX)` | NULL                  | *Ninguno*         | Stacktrace o descripción detallada del error de base de datos o de parseo de Python. |
| `failed_at`         | `DATETIME2(3)`  | NULL                  | `GETDATE()`       | Marca de tiempo en la que se registró el error de procesamiento.                     |

### 3. SdkSourceEvent

Actúa como índice maestro y puente de auditoría relacional, vinculando cada registro crudo de `SentianceEventos` con los registros normalizados en las tablas de dominio. La idea es poder purgar periódicamente la tabla SentianceEventos para que no crezca indefinidamente.

| Campo                  | Tipo de Datos  | Claves / Nulabilidad  | Valor por Defecto | Descripción y Propósito Conceptual                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| ---------------------- | -------------- | --------------------- | ----------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `sdk_source_event_id`  | `BIGINT`       | PRIMARY KEY, NOT NULL | `IDENTITY(1,1)`   | Identificador interno único del evento origen normalizado.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| `sentiance_eventos_id` | `BIGINT`       | NOT NULL              | *Ninguno*         | Referencia obligatoria (Foreign Key conceptual) al `id` original de `SentianceEventos`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| `record_type`          | `VARCHAR(32)`  | NULL                  | *Ninguno*         | Clasificación del registro procesado (ej. `DrivingInsights`, `TimelineUpdate, etc.`).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| `sentiance_user_id`    | `VARCHAR(64)`  | NULL                  | *Ninguno*         | Identificador único provisto por Sentiance para el usuario de la app.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| `source_time`          | `DATETIME2(3)` | NULL                  | *Ninguno*         | Fecha y hora de creación del evento en el origen (SDK de Sentiance).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| `source_event_ref`     | `VARCHAR(64)`  | NULL                  | *Ninguno*         | Identificador de referencia externa provisto por Sentiance utilizado para rastreabilidad y auditoría rápida y para deduplicación e idempotencia:- En `DrivingInsights`**:** Almacena el `transportEvent.id` (el ID canónico del viaje).- En `TimelineEvents` / `UserContextUpdate`**:** Almacena el `event_id` del evento del SDK (por ejemplo, el ID del tramo `IN_TRANSPORT` o `STATIONARY`).- En** **`VehicleCrash`**:** Almacena el ID del evento de choque.- Si el payload no tiene identificador nativo: Cae por defecto en el `id` autoincremental de la tabla de aterrizaje cruda `SentianceEventos`. |
| `payload_hash`         | `VARCHAR(64)`  | NULL                  | *Ninguno*         | Firma hash MD5/SHA de verificación de integridad del payload.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| `created_at`           | `DATETIME2(3)` | NULL                  | `GETDATE()`       | Marca de tiempo en que se generó la entrada de auditoría relacional.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |

### 4. UserMetadata

Permite asociar campos personalizados o metadatos de configuración de negocio a cada ID de usuario registrado en la base. Actualmente no se usa pero se la crea por potenciales usos futuros.

| Campo               | Tipo de Datos   | Claves / Nulabilidad  | Valor por Defecto | Descripción y Propósito Conceptual                                    |
| ------------------- | --------------- | --------------------- | ----------------- | --------------------------------------------------------------------- |
| `metadata_id`       | `BIGINT`        | PRIMARY KEY, NOT NULL | `IDENTITY(1,1)`   | Identificador del registro de metadatos.                              |
| `sentiance_user_id` | `VARCHAR(64)`   | NOT NULL              | *Ninguno*         | Identificador único del usuario de Sentiance.                         |
| `label`             | `VARCHAR(255)`  | NULL                  | *Ninguno*         | Nombre descriptivo del metadato (ej. `device_model`, `driver_group`). |
| `value`             | `NVARCHAR(MAX)` | NULL                  | *Ninguno*         | Valor asignado a la etiqueta de metadatos del usuario.                |
| `updated_at`        | `DATETIME2(3)`  | NULL                  | `GETDATE()`       | Última actualización registrada de esta variable de metadatos.        |

### 5. Trip

Tabla central consolidada de transportes y desplazamientos. Almacena las características geográficas y temporales del viaje.

| Campo                                 | Tipo de Datos    | Claves / Nulabilidad  | Valor por Defecto | Descripción y Propósito Conceptual                                                                                                                                      |
| ------------------------------------- | ---------------- | --------------------- | ----------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `trip_id`                             | `BIGINT`         | PRIMARY KEY, NOT NULL | `IDENTITY(1,1)`   | Identificador incremental del viaje normalizado en base de datos.                                                                                                       |
| `sentiance_user_id`                   | `VARCHAR(64)`    | NOT NULL              | *Ninguno*         | Identificador único del usuario de Sentiance.                                                                                                                           |
| `canonical_transport_event_id`        | `VARCHAR(64)`    | NOT NULL              | *Ninguno*         | ID canónico del viaje asignado por Sentiance (vincula múltiples eventos hijos).                                                                                         |
| `first_seen_from`                     | `VARCHAR(32)`    | NULL                  | *Ninguno*         | Origen de la primera detección del viaje (ej. `UserContextUpdate` o `DrivingInsights`) ya que un mismo viaje puede aparecer en más de un registro.                      |
| `transport_mode`                      | `VARCHAR(32)`    | NULL                  | *Ninguno*         | Modo de transporte clasificado (ej. `CAR`, `WALK`, `RUN`, `BICYCLE`, `TRAIN`).                                                                                          |
| `start_time`                          | `DATETIME2(3)`   | NULL                  | *Ninguno*         | Fecha y hora de inicio del viaje.                                                                                                                                       |
| `start_time_epoch`                    | `BIGINT`         | NULL                  | *Ninguno*         | Marca de tiempo Unix de inicio en milisegundos.                                                                                                                         |
| `last_update_time`                    | `DATETIME2(3)`   | NULL                  | *Ninguno*         | Fecha y hora de la última modificación registrada en el transcurso del viaje.                                                                                           |
| `last_update_time_epoch`              | `BIGINT`         | NULL                  | *Ninguno*         | Unix timestamp del último estado del viaje en milisegundos.                                                                                                             |
| `end_time`                            | `DATETIME2(3)`   | NULL                  | *Ninguno*         | Fecha y hora del fin del viaje.                                                                                                                                         |
| `end_time_epoch`                      | `BIGINT`         | NULL                  | *Ninguno*         | Marca de tiempo Unix de finalización en milisegundos.                                                                                                                   |
| `duration_in_seconds`                 | `NUMERIC(10,0)`  | NULL                  | *Ninguno*         | Duración calculada neta del desplazamiento en segundos.                                                                                                                 |
| `distance_meters`                     | `NUMERIC(12,2)`  | NULL                  | *Ninguno*         | Distancia calculada recorrida expresada en metros.                                                                                                                      |
| `occupant_role`                       | `VARCHAR(32)`    | NULL                  | *Ninguno*         | Rol del usuario en el vehículo (ej. `DRIVER`, `PASSENGER`).                                                                                                             |
| `is_provisional`                      | `BIT`            | NULL                  | `0`               | Flag que indica si el viaje es provisional (actualizado dinámicamente por SDK). Hoy esta columna va a estar siempre en 0 pero se la crea para eventuales usos a futuro. |
| `transport_tags_json`                 | `VARBINARY(MAX)` | NULL                  | *Ninguno*         | JSON serializado binario de etiquetas contextuales (ej. tags de autopistas, congestión). Actualmente no se utiliza.                                                     |
| `waypoints_json`                      | `VARBINARY(MAX)` | NULL                  | *Ninguno*         | Lista de waypoints geográficos comprimida en formato binario (lat, lon, time).                                                                                          |
| `start_location_json`                 | `VARCHAR(255)`   | NULL                  | *Ninguno*         | Dirección textual geocodificada del punto de partida.                                                                                                                   |
| `end_location_json`                   | `VARCHAR(255)`   | NULL                  | *Ninguno*         | Dirección textual geocodificada del punto de destino.                                                                                                                   |
| `creating_sdk_source_event_id`        | `BIGINT`         | FOREIGN KEY, NULL     | *Ninguno*         | Referencia al evento origen en `SdkSourceEvent` que insertó el viaje.                                                                                                   |
| `last_updated_by_sdk_source_event_id` | `BIGINT`         | FOREIGN KEY, NULL     | *Ninguno*         | Referencia al evento en `SdkSourceEvent` que aplicó la última actualización.                                                                                            |
| `created_at`                          | `DATETIME2(3)`   | NULL                  | `GETDATE()`       | Marca de tiempo de registro en base de datos.                                                                                                                           |
| `updated_at`                          | `DATETIME2(3)`   | NULL                  | `GETDATE()`       | Marca de tiempo del último cambio en el registro relacional.                                                                                                            |

### 6. DrivingInsightsTrip

Contiene el consolidado de puntuaciones de seguridad vial calculados por los modelos analíticos de Sentiance para un viaje completado.

| Campo                          | Tipo de Datos    | Claves / Nulabilidad  | Valor por Defecto | Descripción y Propósito Conceptual                                                   |
| ------------------------------ | ---------------- | --------------------- | ----------------- | ------------------------------------------------------------------------------------ |
| `driving_insights_trip_id`     | `BIGINT`         | PRIMARY KEY, NOT NULL | `IDENTITY(1,1)`   | Identificador del registro de Insights del viaje.                                    |
| `sdk_source_event_id`          | `BIGINT`         | NOT NULL              | *Ninguno*         | Identificador del evento origen que contenía los datos de Insights.                  |
| `trip_id`                      | `BIGINT`         | NULL                  | *Ninguno*         | Enlace relacional directo al ID del viaje en la tabla `Trip`.                        |
| `sentiance_user_id`            | `VARCHAR(64)`    | NULL                  | *Ninguno*         | Identificador único del usuario de Sentiance.                                        |
| `canonical_transport_event_id` | `VARCHAR(64)`    | NULL                  | *Ninguno*         | ID del evento de transporte asignado por Sentiance.                                  |
| `smooth_score`                 | `NUMERIC(4,3)`   | NULL                  | *Ninguno*         | Puntuación de conducción suave (0.000 a 1.000). Afectada por maniobras bruscas.      |
| `focus_score`                  | `NUMERIC(4,3)`   | NULL                  | *Ninguno*         | Puntuación de concentración (0.000 a 1.000). Afectada por uso de pantalla del móvil. |
| `legal_score`                  | `NUMERIC(4,3)`   | NULL                  | *Ninguno*         | Puntuación de apego a límites de velocidad (0.000 a 1.000).                          |
| `call_while_moving_score`      | `NUMERIC(4,3)`   | NULL                  | *Ninguno*         | Puntuación asociada a realizar llamadas con el vehículo en movimiento.               |
| `overall_score`                | `NUMERIC(4,3)`   | NULL                  | *Ninguno*         | Índice de seguridad global unificado para el trayecto (0.000 a 1.000).               |
| `harsh_braking_score`          | `NUMERIC(4,3)`   | NULL                  | *Ninguno*         | Sub-puntuación específica para frenadas bruscas.                                     |
| `harsh_turning_score`          | `NUMERIC(4,3)`   | NULL                  | *Ninguno*         | Sub-puntuación específica para giros o curvas agresivas.                             |
| `harsh_acceleration_score`     | `NUMERIC(4,3)`   | NULL                  | *Ninguno*         | Sub-puntuación específica para aceleraciones bruscas.                                |
| `wrong_way_driving_score`      | `NUMERIC(4,3)`   | NULL                  | *Ninguno*         | Sub-puntuación relacionada con conducción en sentido contrario a la vía.             |
| `attention_score`              | `NUMERIC(4,3)`   | NULL                  | *Ninguno*         | Nivel general de atención detectado (0.000 a 1.000).                                 |
| `distance_meters`              | `NUMERIC(12,2)`  | NULL                  | *Ninguno*         | Distancia calculada en metros según telemetría de driving insights.                  |
| `occupant_role`                | `VARCHAR(32)`    | NULL                  | *Ninguno*         | Rol estimado del usuario durante el viaje de insights (DRIVER/PASSENGER).            |
| `transport_tags_json`          | `VARBINARY(MAX)` | NULL                  | *Ninguno*         | Etiquetas específicas de infraestructura vial comprimidas. (Uso futuro)              |
| `created_at`                   | `DATETIME2(3)`   | NULL                  | `GETDATE()`       | Fecha de registro interno.                                                           |

### 7. DrivingInsightsHarshEvent

Registro individualizado de maniobras bruscas (aceleración, frenado o giros agresivos) registradas en un viaje.

| Campo                      | Tipo de Datos    | Claves / Nulabilidad  | Valor por Defecto | Descripción y Propósito Conceptual                                                                                                                           |
| -------------------------- | ---------------- | --------------------- | ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `harsh_event_id`           | `BIGINT`         | PRIMARY KEY, NOT NULL | `IDENTITY(1,1)`   | ID de la maniobra brusca registrada.                                                                                                                         |
| `sdk_source_event_id`      | `BIGINT`         | NOT NULL              | *Ninguno*         | Evento del SDK que reportó el incidente.                                                                                                                     |
| `driving_insights_trip_id` | `BIGINT`         | NOT NULL              | *Ninguno*         | Enlace relacional directo al ID de viaje de insights en `DrivingInsightsTrip`.                                                                               |
| `start_time`               | `DATETIME2(3)`   | NULL                  | *Ninguno*         | Fecha y hora de inicio de la maniobra física.                                                                                                                |
| `start_time_epoch`         | `BIGINT`         | NULL                  | *Ninguno*         | Timestamp Unix de inicio de la maniobra en milisegundos.                                                                                                     |
| `end_time`                 | `DATETIME2(3)`   | NULL                  | *Ninguno*         | Fecha y hora de cese de la fuerza inercial anómala.                                                                                                          |
| `end_time_epoch`           | `BIGINT`         | NULL                  | *Ninguno*         | Timestamp Unix del fin de la maniobra en milisegundos.                                                                                                       |
| `magnitude`                | `NUMERIC(6,3)`   | NULL                  | *Ninguno*         | Magnitud de aceleración (expresada en m/s²).                                                                                                                 |
| `confidence`               | `NUMERIC(5,3)`   | NULL                  | *Ninguno*         | Probabilidad matemática de que el evento sea real (0.000 a 1.000). El SDK de Sentiance devuelve este valor como `int` (0–100); se almacena dividido por 100. |
| `harsh_type`               | `VARCHAR(32)`    | NULL                  | *Ninguno*         | Categoría de la maniobra (`ACCELERATION`, `BRAKING`, `TURN`).                                                                                                |
| `waypoints_json`           | `VARBINARY(MAX)` | NULL                  | *Ninguno*         | Ubicación geográfica exacta de la maniobra en formato binario estructurado.                                                                                  |

### 8. DrivingInsightsPhoneEvent

Intervalos en los que se detecta manipulación o pantalla encendida del móvil durante la conducción.

| Campo                      | Tipo de Datos    | Claves / Nulabilidad  | Valor por Defecto | Descripción y Propósito Conceptual                              |
| -------------------------- | ---------------- | --------------------- | ----------------- | --------------------------------------------------------------- |
| `phone_event_id`           | `BIGINT`         | PRIMARY KEY, NOT NULL | `IDENTITY(1,1)`   | ID único del evento de uso físico de celular.                   |
| `sdk_source_event_id`      | `BIGINT`         | NOT NULL              | *Ninguno*         | Evento del SDK que reportó la distracción.                      |
| `driving_insights_trip_id` | `BIGINT`         | NOT NULL              | *Ninguno*         | FK de referencia al viaje analizado en `DrivingInsightsTrip`.   |
| `start_time`               | `DATETIME2(3)`   | NULL                  | *Ninguno*         | Fecha y hora del inicio de manipulación.                        |
| `start_time_epoch`         | `BIGINT`         | NULL                  | *Ninguno*         | Unix timestamp de inicio de la distracción.                     |
| `end_time`                 | `DATETIME2(3)`   | NULL                  | *Ninguno*         | Fecha y hora en que se bloqueó el móvil o cesó la manipulación. |
| `end_time_epoch`           | `BIGINT`         | NULL                  | *Ninguno*         | Unix timestamp de finalización.                                 |
| `call_state`               | `VARCHAR(32)`    | NULL                  | *Ninguno*         | Estado de interacción (`IN_HAND`, `MOUNTED`, etc.).             |
| `waypoints_json`           | `VARBINARY(MAX)` | NULL                  | *Ninguno*         | Waypoints correspondientes al segmento de distracción.          |

### 9. DrivingInsightsCallEvent

Llamadas telefónicas de voz realizadas con el vehículo en movimiento, indicando el tipo de dispositivo de audio utilizado.

| Campo                      | Tipo de Datos    | Claves / Nulabilidad  | Valor por Defecto | Descripción y Propósito Conceptual                                 |
| -------------------------- | ---------------- | --------------------- | ----------------- | ------------------------------------------------------------------ |
| `call_event_id`            | `BIGINT`         | PRIMARY KEY, NOT NULL | `IDENTITY(1,1)`   | Identificador del evento de llamada.                               |
| `sdk_source_event_id`      | `BIGINT`         | NOT NULL              | *Ninguno*         | Evento origen.                                                     |
| `driving_insights_trip_id` | `BIGINT`         | NOT NULL              | *Ninguno*         | FK al viaje analizado en `DrivingInsightsTrip`.                    |
| `start_time`               | `DATETIME2(3)`   | NULL                  | *Ninguno*         | Fecha y hora del inicio de la llamada.                             |
| `start_time_epoch`         | `BIGINT`         | NULL                  | *Ninguno*         | Unix timestamp de inicio de la llamada.                            |
| `end_time`                 | `DATETIME2(3)`   | NULL                  | *Ninguno*         | Fecha y hora del fin de la llamada.                                |
| `end_time_epoch`           | `BIGINT`         | NULL                  | *Ninguno*         | Unix timestamp del fin de la llamada.                              |
| `min_traveled_speed_mps`   | `NUMERIC(7,2)`   | NULL                  | *Ninguno*         | Velocidad mínima del vehículo en m/s durante la llamada.           |
| `max_traveled_speed_mps`   | `NUMERIC(7,2)`   | NULL                  | *Ninguno*         | Velocidad máxima del vehículo en m/s durante la llamada.           |
| `hands_free_state`         | `VARCHAR(32)`    | NULL                  | *Ninguno*         | Indica el uso de audífonos o bluetooth (`HANDS_FREE`, `HANDHELD`). |
| `waypoints_json`           | `VARBINARY(MAX)` | NULL                  | *Ninguno*         | Segmento de trayectoria donde se mantuvo la llamada.               |

### 10. DrivingInsightsSpeedingEvent

Registra segmentos temporales específicos donde el conductor excedió el límite legal de velocidad establecido para la vía.

| Campo                      | Tipo de Datos    | Claves / Nulabilidad  | Valor por Defecto | Descripción y Propósito Conceptual                                                                                                                                                          |
| -------------------------- | ---------------- | --------------------- | ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `speeding_event_id`        | `BIGINT`         | PRIMARY KEY, NOT NULL | `IDENTITY(1,1)`   | ID del evento de exceso de velocidad.                                                                                                                                                       |
| `sdk_source_event_id`      | `BIGINT`         | NOT NULL              | *Ninguno*         | Evento origen.                                                                                                                                                                              |
| `driving_insights_trip_id` | `BIGINT`         | NOT NULL              | *Ninguno*         | FK al viaje en `DrivingInsightsTrip`.                                                                                                                                                       |
| `start_time`               | `DATETIME2(3)`   | NULL                  | *Ninguno*         | Fecha y hora de inicio de la infracción de velocidad.                                                                                                                                       |
| `start_time_epoch`         | `BIGINT`         | NULL                  | *Ninguno*         | Unix timestamp de inicio.                                                                                                                                                                   |
| `end_time`                 | `DATETIME2(3)`   | NULL                  | *Ninguno*         | Fecha y hora en que se regresó a la velocidad permitida.                                                                                                                                    |
| `end_time_epoch`           | `BIGINT`         | NULL                  | *Ninguno*         | Unix timestamp de finalización.                                                                                                                                                             |
| `waypoints_json`           | `VARBINARY(MAX)` | NULL                  | *Ninguno*         | Lista de waypoints binarios del tramo de exceso de velocidad. Cada waypoint contiene coordenadas geográficas, la velocidad real del transporte y el límite de velocidad legal en ese punto. |

### 11. DrivingInsightsWrongWayDrivingEvent

Registra eventos de circulación en sentido contrario al sentido de la calle o autopista por donde transita el vehículo.

| Campo                      | Tipo de Datos    | Claves / Nulabilidad  | Valor por Defecto | Descripción y Propósito Conceptual                                                                                                                                                              |
| -------------------------- | ---------------- | --------------------- | ----------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `wrong_way_event_id`       | `BIGINT`         | PRIMARY KEY, NOT NULL | `IDENTITY(1,1)`   | Identificador del evento de contramano.                                                                                                                                                         |
| `sdk_source_event_id`      | `BIGINT`         | NOT NULL              | *Ninguno*         | Evento origen.                                                                                                                                                                                  |
| `driving_insights_trip_id` | `BIGINT`         | NOT NULL              | *Ninguno*         | FK de enlace al viaje de insights en `DrivingInsightsTrip`.                                                                                                                                     |
| `start_time`               | `DATETIME2(3)`   | NULL                  | *Ninguno*         | Inicio del trayecto en sentido contrario.                                                                                                                                                       |
| `start_time_epoch`         | `BIGINT`         | NULL                  | *Ninguno*         | Unix timestamp de inicio.                                                                                                                                                                       |
| `end_time`                 | `DATETIME2(3)`   | NULL                  | *Ninguno*         | Fin de la circulación incorrecta.                                                                                                                                                               |
| `end_time_epoch`           | `BIGINT`         | NULL                  | *Ninguno*         | Unix timestamp de cese.                                                                                                                                                                         |
| `waypoints_json`           | `VARBINARY(MAX)` | NULL                  | *Ninguno*         | Lista de waypoints binarios del segmento circulado a contramano. Cada waypoint contiene las coordenadas geográficas del tramo incorrecto. Estructura idéntica a `DrivingInsightsSpeedingEvent`. |

### 12. UserContextHeader

Encabezado de eventos de cambio de contexto del usuario, capturando ubicación física instantánea y datos de semántica temporal.

| Campo                     | Tipo de Datos   | Claves / Nulabilidad  | Valor por Defecto | Descripción y Propósito Conceptual                          |
| ------------------------- | --------------- | --------------------- | ----------------- | ----------------------------------------------------------- |
| `user_context_payload_id` | `BIGINT`        | PRIMARY KEY, NOT NULL | `IDENTITY(1,1)`   | Identificador de cabecera del payload de contexto.          |
| `sdk_source_event_id`     | `BIGINT`        | NOT NULL              | *Ninguno*         | FK origen en `SdkSourceEvent`.                              |
| `sentiance_user_id`       | `VARCHAR(64)`   | NULL                  | *Ninguno*         | ID del usuario de Sentiance.                                |
| `context_source_type`     | `VARCHAR(32)`   | NULL                  | *Ninguno*         | Origen del contexto (ej. `LISTENER, MANUAL`).               |
| `semantic_time`           | `VARCHAR(32)`   | NULL                  | *Ninguno*         | Categoría de tiempo semántico (ej. `EVENING`, `AFTERNOON`). |
| `last_known_latitude`     | `DECIMAL(10,8)` | NULL                  | *Ninguno*         | Última latitud registrada del dispositivo.                  |
| `last_known_longitude`    | `DECIMAL(11,8)` | NULL                  | *Ninguno*         | Última longitud registrada del dispositivo.                 |
| `last_known_accuracy`     | `NUMERIC(12,2)` | NULL                  | *Ninguno*         | Margen de error de la localización en metros.               |
| `created_at`              | `DATETIME2(3)`  | NULL                  | `GETDATE()`       | Fecha de registro interno.                                  |

### 13. UserContextUpdateCriteria

Almacena la lista de motivos o disparadores técnicos por los cuales el motor del SDK actualizó el contexto del usuario.

| Campo                             | Tipo de Datos | Claves / Nulabilidad  | Valor por Defecto | Descripción y Propósito Conceptual                                                 |
| --------------------------------- | ------------- | --------------------- | ----------------- | ---------------------------------------------------------------------------------- |
| `user_context_update_criteria_id` | `BIGINT`      | PRIMARY KEY, NOT NULL | `IDENTITY(1,1)`   | Identificador único del criterio registrado.                                       |
| `user_context_payload_id`         | `BIGINT`      | NOT NULL              | *Ninguno*         | FK apuntando a la cabecera correspondiente en `UserContextHeader`.                 |
| `criteria_code`                   | `VARCHAR(32)` | NULL                  | *Ninguno*         | Código técnico del gatillador (ej. CURRENT_EVENT, VISITED_VENUES, MANUAL_REQUEST). |

### 14. UserHomeHistory

Detalle del venue geográfico del usuario clasificado e inferido por Sentiance como su lugar de residencia ("Casa").

| Campo                     | Tipo de Datos   | Claves / Nulabilidad  | Valor por Defecto | Descripción y Propósito Conceptual                       |
| ------------------------- | --------------- | --------------------- | ----------------- | -------------------------------------------------------- |
| `user_home_history_id`    | `BIGINT`        | PRIMARY KEY, NOT NULL | `IDENTITY(1,1)`   | ID incremental del registro de residencia.               |
| `user_context_payload_id` | `BIGINT`        | NOT NULL              | *Ninguno*         | FK al payload origen en `UserContextHeader`.             |
| `significance`            | `VARCHAR(32)`   | NULL                  | *Ninguno*         | Indicador cualitativo de relevancia del venue.           |
| `venue_type`              | `VARCHAR(32)`   | NULL                  | *Ninguno*         | Clasificación del establecimiento (`HOME, RESIDENTIAL`). |
| `latitude`                | `DECIMAL(10,8)` | NULL                  | *Ninguno*         | Latitud del centroide estimado de la residencia.         |
| `longitude`               | `DECIMAL(11,8)` | NULL                  | *Ninguno*         | Longitud del centroide estimado de la residencia.        |
| `accuracy`                | `NUMERIC(12,2)` | NULL                  | *Ninguno*         | Radio de confianza/precisión estimado en metros.         |

### 15. UserWorkHistory

Detalle del venue geográfico del usuario clasificado e inferido por Sentiance como su lugar laboral ("Trabajo").

| Campo                     | Tipo de Datos   | Claves / Nulabilidad  | Valor por Defecto | Descripción y Propósito Conceptual                 |
| ------------------------- | --------------- | --------------------- | ----------------- | -------------------------------------------------- |
| `user_work_history_id`    | `BIGINT`        | PRIMARY KEY, NOT NULL | `IDENTITY(1,1)`   | ID incremental del lugar de trabajo.               |
| `user_context_payload_id` | `BIGINT`        | NOT NULL              | *Ninguno*         | FK al payload origen en `UserContextHeader`.       |
| `significance`            | `VARCHAR(32)`   | NULL                  | *Ninguno*         | Relevancia del establecimiento.                    |
| `venue_type`              | `VARCHAR(32)`   | NULL                  | *Ninguno*         | Clasificación (`OFFICE, HEALTH, INDUSTRIAL, etc`). |
| `latitude`                | `DECIMAL(10,8)` | NULL                  | *Ninguno*         | Latitud del centroide del lugar laboral.           |
| `longitude`               | `DECIMAL(11,8)` | NULL                  | *Ninguno*         | Longitud del centroide del lugar laboral.          |
| `accuracy`                | `NUMERIC(12,2)` | NULL                  | *Ninguno*         | Radio de confianza/precisión estimado en metros.   |

### 16. UserContextActiveSegmentDetail

Segmentos demográficos o de estilo de vida inferidos del perfil de usuario activos en el momento del evento.

| Campo                                   | Tipo de Datos  | Claves / Nulabilidad  | Valor por Defecto | Descripción y Propósito Conceptual                              |
| --------------------------------------- | -------------- | --------------------- | ----------------- | --------------------------------------------------------------- |
| `user_context_active_segment_detail_id` | `BIGINT`       | PRIMARY KEY, NOT NULL | `IDENTITY(1,1)`   | Identificador del segmento activo.                              |
| `user_context_payload_id`               | `BIGINT`       | NOT NULL              | *Ninguno*         | FK al payload origen en `UserContextHeader`.                    |
| `sentiance_user_id`                     | `VARCHAR(64)`  | NULL                  | *Ninguno*         | ID del usuario de Sentiance.                                    |
| `segment_id`                            | `VARCHAR(64)`  | NULL                  | *Ninguno*         | ID técnico del segmento asignado.                               |
| `category`                              | `VARCHAR(32)`  | NULL                  | *Ninguno*         | Categoría del perfil del usuario (ej. `MOBILITY`, `LIFESTYLE`). |
| `subcategory`                           | `VARCHAR(32)`  | NULL                  | *Ninguno*         | Subcategoría de afinidad (ej. `COMMUTER`, `SHOPPER`).           |
| `segment_type`                          | `VARCHAR(32)`  | NULL                  | *Ninguno*         | Nombre del perfil específico (ej. `CAR_DRIVER`, `TOWN_BOUND`).  |
| `start_time`                            | `DATETIME2(3)` | NULL                  | *Ninguno*         | Fecha de inicio del segmento activo.                            |
| `start_time_epoch`                      | `BIGINT`       | NULL                  | *Ninguno*         | Unix timestamp de inicio.                                       |
| `end_time`                              | `DATETIME2(3)` | NULL                  | *Ninguno*         | Fecha estimada de vencimiento de este segmento del perfil.      |
| `end_time_epoch`                        | `BIGINT`       | NULL                  | *Ninguno*         | Unix timestamp de vencimiento.                                  |
| `created_at`                            | `DATETIME2(3)` | NULL                  | `GETDATE()`       | Fecha de almacenamiento.                                        |

### 17. UserContextSegmentAttribute

Atributos numéricos de afinidad que cuantifican la probabilidad de pertenencia a un perfil segmentado activo.

| Campo                                   | Tipo de Datos   | Claves / Nulabilidad  | Valor por Defecto | Descripción y Propósito Conceptual                                    |
| --------------------------------------- | --------------- | --------------------- | ----------------- | --------------------------------------------------------------------- |
| `user_context_segment_attr_id`          | `BIGINT`        | PRIMARY KEY, NOT NULL | `IDENTITY(1,1)`   | ID del atributo de afinidad.                                          |
| `user_context_active_segment_detail_id` | `BIGINT`        | NOT NULL              | *Ninguno*         | FK de referencia al segmento en `UserContextActiveSegmentDetail`.     |
| `attribute_name`                        | `VARCHAR(64)`   | NULL                  | *Ninguno*         | Nombre del atributo técnico evaluado (ej. `probability`, `score`).    |
| `attribute_value`                       | `NUMERIC(18,4)` | NULL                  | *Ninguno*         | Valor decimal del score cuantitativo asignado por la IA de Sentiance. |

### Nota: Ejemplo Práctico (tablas 16 y 17)

Si se procesa una actualización de contexto donde se detecta que el usuario pertenece al segmento de conductor agresivo, los registros se verían así:

1. En `UserContextActiveSegmentDetail` (Segmento Padre):
  - `segment_type`: `"AGGRESSIVE_DRIVER"`
  - `category`: `"MOBILITY"`
2. En `UserContextSegmentAttribute` (Atributos Hijos asociados):
  - **Registro 1:** `attribute_name = "score"`, `attribute_value = 0.8450` (indica qué tan marcada es la agresividad).
  - **Registro 2:** `attribute_name = "confidence"`, `attribute_value = 0.9100` (la certeza estadística que tiene el modelo de Sentiance sobre esta clasificación).

Esto permite no solo saber *qué* perfiles tiene el conductor, sino también realizar análisis estadísticos avanzados sobre la **graduación o nivel** de afinidad de cada uno de esos perfiles.  
En otras palabras, UserContextSegmentAttribute es la fundamentación numérica del UserContextActiveSegmentDetail correspondiente.

### 18. UserContextEventDetail

Desglosa el array `events` presente en los payloads de cambio de contexto del usuario (UserContextUpdate). Útil para registrar lapsos estacionarios y de viaje cortos.

| Campo                          | Tipo de Datos    | Claves / Nulabilidad  | Valor por Defecto | Descripción y Propósito Conceptual                                                 |
| ------------------------------ | ---------------- | --------------------- | ----------------- | ---------------------------------------------------------------------------------- |
| `user_context_event_detail_id` | `BIGINT`         | PRIMARY KEY, NOT NULL | `IDENTITY(1,1)`   | ID del evento de contexto detallado.                                               |
| `user_context_payload_id`      | `BIGINT`         | NOT NULL              | *Ninguno*         | FK a la cabecera correspondiente en `UserContextHeader`.                           |
| `sentiance_user_id`            | `VARCHAR(64)`    | NULL                  | *Ninguno*         | ID del usuario de Sentiance.                                                       |
| `event_id`                     | `VARCHAR(64)`    | NULL                  | *Ninguno*         | ID único del evento generado por el SDK.                                           |
| `event_type`                   | `VARCHAR(32)`    | NULL                  | *Ninguno*         | Tipo de evento (`STATIONARY`, `IN_TRANSPORT`, etc.).                               |
| `start_time`                   | `DATETIME2(3)`   | NULL                  | *Ninguno*         | Fecha y hora de inicio de la actividad de contexto.                                |
| `start_time_epoch`             | `BIGINT`         | NULL                  | *Ninguno*         | Unix timestamp de inicio.                                                          |
| `last_update_time`             | `DATETIME2(3)`   | NULL                  | *Ninguno*         | Última actualización registrada de la actividad.                                   |
| `last_update_time_epoch`       | `BIGINT`         | NULL                  | *Ninguno*         | Unix timestamp de actualización.                                                   |
| `end_time`                     | `DATETIME2(3)`   | NULL                  | *Ninguno*         | Fecha y hora de término de la actividad.                                           |
| `end_time_epoch`               | `BIGINT`         | NULL                  | *Ninguno*         | Unix timestamp de finalización.                                                    |
| `duration_in_seconds`          | `NUMERIC(10,0)`  | NULL                  | *Ninguno*         | Duración en segundos de la actividad.                                              |
| `is_provisional`               | `BIT`            | NULL                  | *Ninguno*         | Flag que señala si el evento de contexto es interino o final.                      |
| `transport_mode`               | `VARCHAR(32)`    | NULL                  | *Ninguno*         | Modo de transporte clasificado (si aplica).                                        |
| `distance_meters`              | `NUMERIC(12,2)`  | NULL                  | *Ninguno*         | Distancia total recorrida estimada en metros.                                      |
| `occupant_role`                | `VARCHAR(32)`    | NULL                  | *Ninguno*         | Rol del usuario en el vehículo.                                                    |
| `transport_tags_json`          | `VARBINARY(MAX)` | NULL                  | *Ninguno*         | JSON serializado binario de etiquetas del transporte.                              |
| `location_latitude`            | `DECIMAL(10,8)`  | NULL                  | *Ninguno*         | Latitud promedio ponderada de la localización.                                     |
| `location_longitude`           | `DECIMAL(11,8)`  | NULL                  | *Ninguno*         | Longitud promedio ponderada de la localización.                                    |
| `location_accuracy`            | `NUMERIC(12,2)`  | NULL                  | *Ninguno*         | Precisión de geolocalización promedio.                                             |
| `venue_significance`           | `VARCHAR(32)`    | NULL                  | *Ninguno*         | Importancia conceptual si corresponde a una parada fija (ej. `POINT_OF_INTEREST`). |
| `venue_type`                   | `VARCHAR(32)`    | NULL                  | *Ninguno*         | Clasificación del venue visitado (ej. `RESTAURANT`, `PETROL_STATION`).             |
| `created_at`                   | `DATETIME2(3)`   | NULL                  | `GETDATE()`       | Fecha de registro interno.                                                         |

### 19. TimelineEventHistory

Historial consolidado e indexado de la línea de tiempo cronológica completa de eventos recibidos a través del canal `TimelineEvent`.

| Campo                       | Tipo de Datos    | Claves / Nulabilidad  | Valor por Defecto | Descripción y Propósito Conceptual                                     |
| --------------------------- | ---------------- | --------------------- | ----------------- | ---------------------------------------------------------------------- |
| `timeline_event_history_id` | `BIGINT`         | PRIMARY KEY, NOT NULL | `IDENTITY(1,1)`   | ID incremental del registro en la línea de tiempo.                     |
| `sdk_source_event_id`       | `BIGINT`         | NOT NULL              | *Ninguno*         | FK origen en `SdkSourceEvent`.                                         |
| `sentiance_user_id`         | `VARCHAR(64)`    | NULL                  | *Ninguno*         | ID del usuario de Sentiance.                                           |
| `event_id`                  | `VARCHAR(64)`    | NULL                  | *Ninguno*         | ID de evento único provisto por el SDK.                                |
| `event_type`                | `VARCHAR(32)`    | NULL                  | *Ninguno*         | Tipo de evento (`UNKNOWN`, `STATIONARY`, `OFFTHEGRID`, `INTRANSPORT`). |
| `start_time`                | `DATETIME2(3)`   | NULL                  | *Ninguno*         | Fecha y hora de inicio de la actividad en la línea de tiempo.          |
| `start_time_epoch`          | `BIGINT`         | NULL                  | *Ninguno*         | Unix timestamp de inicio.                                              |
| `last_update_time`          | `DATETIME2(3)`   | NULL                  | *Ninguno*         | Última actualización registrada de este evento de timeline.            |
| `last_update_time_epoch`    | `BIGINT`         | NULL                  | *Ninguno*         | Unix timestamp de actualización.                                       |
| `end_time`                  | `DATETIME2(3)`   | NULL                  | *Ninguno*         | Fecha y hora de cese.                                                  |
| `end_time_epoch`            | `BIGINT`         | NULL                  | *Ninguno*         | Unix timestamp de cese.                                                |
| `duration_in_seconds`       | `NUMERIC(10,0)`  | NULL                  | *Ninguno*         | Duración total acumulada neta del tramo temporal en segundos.          |
| `is_provisional`            | `BIT`            | NULL                  | *Ninguno*         | Flag que señala si el evento de timeline es parcial o ya está cerrado. |
| `transport_mode`            | `VARCHAR(32)`    | NULL                  | *Ninguno*         | Modo de locomoción detectado si corresponde a `INTRANSPORT`.           |
| `distance_meters`           | `NUMERIC(12,2)`  | NULL                  | *Ninguno*         | Distancia geodésica acumulada en metros.                               |
| `occupant_role`             | `VARCHAR(32)`    | NULL                  | *Ninguno*         | Rol estimado del usuario.                                              |
| `transport_tags_json`       | `VARBINARY(MAX)` | NULL                  | *Ninguno*         | JSON serializado binario de etiquetas del trayecto.                    |
| `location_latitude`         | `DECIMAL(10,8)`  | NULL                  | *Ninguno*         | Latitud de visita si corresponde a un evento `STATIONARY`.             |
| `location_longitude`        | `DECIMAL(11,8)`  | NULL                  | *Ninguno*         | Longitud de visita si corresponde a un evento `STATIONARY`.            |
| `location_accuracy`         | `NUMERIC(12,2)`  | NULL                  | *Ninguno*         | Radio de error geográfico.                                             |
| `venue_significance`        | `VARCHAR(32)`    | NULL                  | *Ninguno*         | Nivel de importancia determinado para el punto de detención.           |
| `venue_type`                | `VARCHAR(32)`    | NULL                  | *Ninguno*         | Clasificación formal del venue.                                        |
| `created_at`                | `DATETIME2(3)`   | NULL                  | `GETDATE()`       | Fecha de registro interno.                                             |

### 20. UserActivityHistory

Resumen simplificado y de baja latitud diseñado para dashboards ágiles, compilando estados generales de viaje o visitas estacionarias. Es una tabla Legacy que no se usa  probablemente nunca se usa pero se la crea por precaución.

| Campo                      | Tipo de Datos   | Claves / Nulabilidad  | Valor por Defecto | Descripción y Propósito Conceptual                                    |
| -------------------------- | --------------- | --------------------- | ----------------- | --------------------------------------------------------------------- |
| `user_activity_history_id` | `BIGINT`        | PRIMARY KEY, NOT NULL | `IDENTITY(1,1)`   | ID único de actividad agregada.                                       |
| `sdk_source_event_id`      | `BIGINT`        | NOT NULL              | *Ninguno*         | FK origen en `SdkSourceEvent`.                                        |
| `sentiance_user_id`        | `VARCHAR(64)`   | NULL                  | *Ninguno*         | ID del usuario de Sentiance.                                          |
| `activity_type`            | `VARCHAR(32)`   | NULL                  | *Ninguno*         | Categoría de la actividad agregada (`TRIP`, `STATIONARY`, `UNKNOWN`). |
| `trip_type`                | `VARCHAR(32)`   | NULL                  | *Ninguno*         | Subclasificación opcional del tipo de viaje.                          |
| `stationary_latitude`      | `DECIMAL(10,8)` | NULL                  | *Ninguno*         | Latitud donde se concentra la actividad fija (si es `STATIONARY`).    |
| `stationary_longitude`     | `DECIMAL(11,8)` | NULL                  | *Ninguno*         | Longitud donde se concentra la actividad fija (si es `STATIONARY`).   |
| `payload_json`             | `NVARCHAR(MAX)` | NULL                  | *Ninguno*         | Copia JSON auxiliar con campos clave para lectura directa rápida.     |
| `captured_at`              | `DATETIME2(3)`  | NULL                  | `GETDATE()`       | Marca de tiempo de registro interno en base de datos.                 |

### 21. TechnicalEventHistory

Registra eventos técnicos, logs de soporte móvil o métricas de offload de datos del SDK, fundamentales para supervisar la salud del pipeline móvil.

> **Nota de diseño:** Esta tabla no corresponde a ningún tipo de evento nativo del SDK de Sentiance. Es un diseño propio del pipeline ETL para centralizar logs operativos, offloads de datos y métricas de diagnóstico del SDK que no encajan en las tablas de dominio.

| Campo                        | Tipo de Datos   | Claves / Nulabilidad  | Valor por Defecto | Descripción y Propósito Conceptual                                       |
| ---------------------------- | --------------- | --------------------- | ----------------- | ------------------------------------------------------------------------ |
| `technical_event_history_id` | `BIGINT`        | PRIMARY KEY, NOT NULL | `IDENTITY(1,1)`   | ID del evento técnico registrado.                                        |
| `sdk_source_event_id`        | `BIGINT`        | NOT NULL              | *Ninguno*         | FK origen en `SdkSourceEvent`.                                           |
| `sentiance_user_id`          | `VARCHAR(64)`   | NULL                  | *Ninguno*         | ID del usuario de Sentiance.                                             |
| `technical_event_type`       | `VARCHAR(32)`   | NULL                  | *Ninguno*         | Tipo de log operativo (ej. `OFFLOAD_TRIGGERED`, `DIAGNOSTIC_SUBMITTED`). |
| `message`                    | `NVARCHAR(MAX)` | NULL                  | *Ninguno*         | Texto libre o mensaje de log asociado al evento técnico.                 |
| `payload_json`               | `NVARCHAR(MAX)` | NULL                  | *Ninguno*         | Datos estructurados complementarios adjuntos al log.                     |
| `captured_at`                | `DATETIME2(3)`  | NULL                  | `GETDATE()`       | Fecha de inserción.                                                      |

### 22. VehicleCrashEvent

Tabla de alta criticidad operativa destinada a albergar registros detallados de colisiones/choques graves a bordo de vehículos en movimiento.

| Campo                      | Tipo de Datos    | Claves / Nulabilidad  | Valor por Defecto | Descripción y Propósito Conceptual                                              |
| -------------------------- | ---------------- | --------------------- | ----------------- | ------------------------------------------------------------------------------- |
| `vehicle_crash_event_id`   | `BIGINT`         | PRIMARY KEY, NOT NULL | `IDENTITY(1,1)`   | Identificador del choque registrado.                                            |
| `sdk_source_event_id`      | `BIGINT`         | NOT NULL              | *Ninguno*         | FK origen en `SdkSourceEvent`.                                                  |
| `sentiance_user_id`        | `VARCHAR(64)`    | NULL                  | *Ninguno*         | ID del usuario de Sentiance.                                                    |
| `crash_time_epoch`         | `BIGINT`         | NULL                  | *Ninguno*         | Unix timestamp exacto estimado de la colisión en milisegundos.                  |
| `latitude`                 | `DECIMAL(10,8)`  | NULL                  | *Ninguno*         | Latitud geográfica estimada del choque.                                         |
| `longitude`                | `DECIMAL(11,8)`  | NULL                  | *Ninguno*         | Longitud geográfica estimada del choque.                                        |
| `accuracy`                 | `NUMERIC(12,2)`  | NULL                  | *Ninguno*         | Margen de error en metros para la localización del siniestro.                   |
| `altitude`                 | `NUMERIC(10,2)`  | NULL                  | *Ninguno*         | Altitud en metros sobre el nivel del mar donde ocurrió.                         |
| `magnitude`                | `NUMERIC(6,3)`   | NULL                  | *Ninguno*         | Magnitud de impacto físico de la colisión en fuerzas inerciales (G).            |
| `speed_at_impact`          | `NUMERIC(7,2)`   | NULL                  | *Ninguno*         | Velocidad estimada del vehículo al momento del impacto en m/s.                  |
| `delta_v`                  | `NUMERIC(7,2)`   | NULL                  | *Ninguno*         | Variación neta de velocidad instantánea experimentada en la colisión (Delta V). |
| `confidence`               | `NUMERIC(5,3)`   | NULL                  | *Ninguno*         | Factor de confianza matemática sobre la veracidad de la colisión (0 a 1).       |
| `severity`                 | `VARCHAR(32)`    | NULL                  | *Ninguno*         | Gravedad cualitativa asignada al impacto (ej. `MINOR`, `MODERATE`, `SEVERE`).   |
| `detector_mode`            | `VARCHAR(32)`    | NULL                  | *Ninguno*         | Algoritmo que lo gatilló (ej. `HIGH_G_ACCELEROMETER`, `IMPACT_FUSION`).         |
| `preceding_locations_json` | `VARBINARY(MAX)` | NULL                  | *Ninguno*         | Trayectoria y coordenadas inmediatas previas al impacto (JSON en binario).      |

### 23. SdkStatusHistory

Almacena capturas temporales sobre el estado operativo, nivel de batería, y permisos del dispositivo que corre el SDK móvil.

| Campo                      | Tipo de Datos  | Claves / Nulabilidad  | Valor por Defecto | Descripción y Propósito Conceptual                                                                     |
| -------------------------- | -------------- | --------------------- | ----------------- | ------------------------------------------------------------------------------------------------------ |
| `sdk_status_history_id`    | `BIGINT`       | PRIMARY KEY, NOT NULL | `IDENTITY(1,1)`   | Identificador del log de estado del SDK.                                                               |
| `sdk_source_event_id`      | `BIGINT`       | NOT NULL              | *Ninguno*         | FK origen en `SdkSourceEvent`.                                                                         |
| `sentiance_user_id`        | `VARCHAR(64)`  | NULL                  | *Ninguno*         | ID del usuario de Sentiance.                                                                           |
| `start_status`             | `VARCHAR(32)`  | NULL                  | *Ninguno*         | Estado de inicio del SDK (ej. `STARTED`, `STOPPED`).                                                   |
| `detection_status`         | `VARCHAR(32)`  | NULL                  | *Ninguno*         | Estado operativo de detección. Valores: `DETECTING`, `NOT_DETECTING`, `DISABLED`, `EXPIRED_DETECTION`. |
| `location_permission`      | `VARCHAR(32)`  | NULL                  | *Ninguno*         | Nivel de permisos otorgados en el móvil (ej. `ALWAYS`, `WHILE_IN_USE`).                                |
| `precise_location_granted` | `BIT`          | NULL                  | *Ninguno*         | Flag que señala si el móvil cedió localización de alta precisión (GPS).                                |
| `is_location_available`    | `BIT`          | NULL                  | *Ninguno*         | Flag técnico de accesibilidad instantánea al hardware de posicionamiento.                              |
| `quota_status_wifi`        | `VARCHAR(32)`  | NULL                  | *Ninguno*         | Límite o cuota de red Wi-Fi disponible.                                                                |
| `quota_status_mobile`      | `VARCHAR(32)`  | NULL                  | *Ninguno*         | Límite o cuota de consumo de red móvil (datos celulares).                                              |
| `quota_status_disk`        | `VARCHAR(32)`  | NULL                  | *Ninguno*         | Espacio/Cuota física libre asignada en el dispositivo del usuario.                                     |
| `can_detect`               | `BIT`          | NULL                  | *Ninguno*         | Flag unificado que indica si el SDK puede realizar detecciones en segundo plano.                       |
| `captured_at`              | `DATETIME2(3)` | NULL                  | `GETDATE()`       | Fecha de registro interno.                                                                             |

#### Campos del SDK no capturados (decisión de diseño)

El objeto `SdkStatus` del SDK de Sentiance expone 21 propiedades. La tabla almacena 9 de ellas. Los siguientes campos están disponibles en el SDK pero no se persisten en la base de datos:

| Campo SDK                          | Tipo      | Descripción                                                                          |
| ---------------------------------- | --------- | ------------------------------------------------------------------------------------ |
| `isRemoteEnabled`                  | `Boolean` | Si el SDK está habilitado remotamente desde el servidor de Sentiance.                |
| `isActivityRecognitionPermGranted` | `Boolean` | Si el permiso de reconocimiento de actividad física fue concedido en el dispositivo. |
| `isAirplaneModeEnabled`            | `Boolean` | Si el modo avión está activo (interrumpe la detección).                              |
| `isAccelPresent`                   | `Boolean` | Si el acelerómetro está presente y disponible en el hardware del dispositivo.        |
| `isGyroPresent`                    | `Boolean` | Si el giroscopio está presente y disponible en el hardware del dispositivo.          |
| `isGpsPresent`                     | `Boolean` | Si el GPS está presente y disponible en el hardware del dispositivo.                 |
| `isGooglePlayServicesMissing`      | `Boolean` | Si Google Play Services no está disponible (solo Android; afecta la detección).      |
| `isBatteryOptimizationEnabled`     | `Boolean` | Si la optimización de batería del SO está activa (puede restringir el SDK).          |
| `isBatterySavingEnabled`           | `Boolean` | Si el modo ahorro de batería está activo.                                            |
| `isBackgroundProcessingRestricted` | `Boolean` | Si el SO restringe el procesamiento en segundo plano para esta app.                  |
| `isSchedulingExactAlarmsPermitted` | `Boolean` | Si se concedió el permiso de alarmas exactas (requerido en Android 12+).             |

---

### 24. UserOrganization

Tabla de mapeo entre usuarios de Sentiance y organizaciones cliente. Permite filtrar cualquier dato de dominio (viajes, eventos, contexto) por cliente mediante un JOIN sobre `sentiance_user_id`, sin modificar el resto del schema.

> **Diseño multi-tenancy:** un usuario pertenece a una sola organización activa a la vez (constraint UNIQUE sobre `sentiance_user_id`). Si el usuario cambia de organización, la fila existente se actualiza (MERGE). El campo `hasta` permite consultar el historial si se implementa en el futuro.

**Cómo se popula:** el ETL intercepta eventos `UserMetadata` con `label = 'organizacion'` (case-insensitive) y ejecuta un UPSERT en esta tabla además del INSERT normal en `UserMetadata`.

| Campo | Tipo | Nulabilidad | Default | Descripción |
|-------|------|-------------|---------|-------------|
| `user_organization_id` | `BIGINT` | NOT NULL | `IDENTITY` | PK autoincremental. |
| `sentiance_user_id` | `VARCHAR(64)` | NOT NULL | — | ID del usuario en Sentiance. UNIQUE — un usuario = una organización activa. |
| `organizacion` | `VARCHAR(128)` | NOT NULL | — | Nombre de la organización/cliente. Valor proveniente del campo `value` del evento `UserMetadata`. |
| `activo` | `BIT` | NOT NULL | `1` | `1` = relación vigente. Se pone a `0` si en el futuro se implementa soft-delete. |
| `desde` | `DATETIME2(3)` | NOT NULL | `GETDATE()` | Fecha desde la que el usuario pertenece a esta organización. |
| `hasta` | `DATETIME2(3)` | NULL | *Ninguno* | Fecha de baja de la organización. `NULL` = vigente. |

**Índice:** `IX_UserOrganization_Org (organizacion) WHERE activo = 1` — optimiza queries del tipo "todos los usuarios del cliente X".

**Query típico para filtrar trips por organización:**
```sql
SELECT t.*
FROM Trip t
JOIN UserOrganization uo
  ON uo.sentiance_user_id = t.sentiance_user_id AND uo.activo = 1
WHERE uo.organizacion = 'ClienteX'
```
