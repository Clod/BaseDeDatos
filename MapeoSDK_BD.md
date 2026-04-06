# Mapeo SDK Sentiance → Base de Datos

> **Última actualización:** 2026-04-04
> **Motor:** Microsoft SQL Server (T-SQL)
> **Fuente de verdad:** Documentación oficial del SDK React Native de Sentiance + `Entregable.md`

Este documento detalla, **campo por campo**, cómo cada propiedad de los payloads emitidos por los listeners del SDK de Sentiance se persiste en las tablas de la base de datos.

**Convenciones:**

- `→` indica la columna de destino en formato `Tabla.columna`.
- `VARBINARY(MAX)` indica que el campo es serializado/comprimido (GZIP/CBOR) antes de almacenarse; no es directamente consultable con `JSON_VALUE`.
- `[omitido]` indica que el campo existe en el SDK pero fue **excluido intencionalmente** del esquema por decisión de diseño (generalmente por volumen/duplicidad).
- `[sintético]` indica un valor generado por el ETL, no presente en el payload original.

---

## 1. `DrivingInsights`

**Tipo en producción:** `DrivingInsights`
**Equivalente SDK:** `DrivingInsightsReady` (listener `addDrivingInsightsReadyListener`)
**Ref. SDK:** `@sentiance-react-native/driving-insights` — [Definitions](https://docs.sentiance.com/important-topics/sdk/api-reference/react-native/driving-insights/definitions)

El payload del listener `DrivingInsightsReady` es un objeto `DrivingInsights` compuesto por:
- **`transportEvent`**: El evento de transporte completo.
- **`safetyScores`**: Los puntajes de conducción.
- Sub-eventos (obtenidos mediante llamadas auxiliares agregadas al payload por la App): `harshDrivingEvents`, `phoneUsageEvents`, `callEvents`, `speedingEvents`, `wrongWayDrivingEvents`.

### 1.1. Payload raíz (`DrivingInsights`)

| Campo JSON (SDK)            | Tipo SDK     | Tabla destino           | Columna destino              | Notas |
| --------------------------- | ------------ | ----------------------- | ---------------------------- | ----- |
| *(registro crudo)*          | —            | `SentianceEventos`      | `json`                       | El payload completo se almacena aquí antes de ser procesado. |
| *(tipo de registro)*        | —            | `SentianceEventos`      | `tipo`                       | Valor literal: `"DrivingInsights"` |
| *(metadato de proceso)*     | —            | `SdkSourceEvent`        | `record_type`                | `[sintético]` Valor: `"DrivingInsights"` |
| *(metadato de proceso)*     | —            | `SdkSourceEvent`        | `sentiance_user_id`          | `[sintético]` ID del usuario Sentiance |
| *(metadato de proceso)*     | —            | `SdkSourceEvent`        | `source_event_ref`           | `[sintético]` = `transportEvent.id` |
| *(metadato de proceso)*     | —            | `SdkSourceEvent`        | `payload_hash`               | `[sintético]` Hash SHA-256 del payload para deduplicación |

### 1.2. Sub-estructura: `transportEvent` (TransportEvent)

Representa el viaje motorizado al que corresponden los insights.

| Campo JSON (SDK)                  | Tipo SDK       | Tabla destino           | Columna destino                    | Notas |
| --------------------------------- | -------------- | ----------------------- | ---------------------------------- | ----- |
| `transportEvent.id`               | `string`       | `DrivingInsightsTrip`   | `canonical_transport_event_id`     | Clave de unicidad. También se usa en `SdkSourceEvent.source_event_ref` |
| `transportEvent.id`               | `string`       | `Trip`                  | `canonical_transport_event_id`     | Vía MERGE (UPSERT). Clave de deduplicación global del viaje. |
| `transportEvent.startTime`        | `string`       | `Trip`                  | `start_time`                       | ISO 8601 |
| `transportEvent.startTimeEpoch`   | `number`       | `Trip`                  | `start_time_epoch`                 | UTC en milisegundos |
| `transportEvent.lastUpdateTime`   | `string`       | `Trip`                  | `last_update_time`                 | ISO 8601 |
| `transportEvent.lastUpdateTimeEpoch` | `number`    | `Trip`                  | `last_update_time_epoch`           | UTC en milisegundos |
| `transportEvent.endTime`          | `string\|null` | `Trip`                  | `end_time`                         | ISO 8601; null si no finalizó |
| `transportEvent.endTimeEpoch`     | `number\|null` | `Trip`                  | `end_time_epoch`                   | UTC en milisegundos |
| `transportEvent.durationInSeconds`| `number\|null` | `Trip`                  | `duration_in_seconds`              | Duración en segundos |
| `transportEvent.transportMode`    | `TransportMode\|null` | `Trip`           | `transport_mode`                   | Enum: `"CAR"`, `"BUS"`, `"MOTORCYCLE"`, etc. |
| `transportEvent.distance`         | `number`       | `DrivingInsightsTrip`   | `distance_meters`                  | En metros |
| `transportEvent.distance`         | `number`       | `Trip`                  | `distance_meters`                  | En metros (vía MERGE) |
| `transportEvent.occupantRole`     | `OccupantRole` | `DrivingInsightsTrip`   | `occupant_role`                    | `"DRIVER"`, `"PASSENGER"`, `"UNAVAILABLE"` |
| `transportEvent.occupantRole`     | `OccupantRole` | `Trip`                  | `occupant_role`                    | Idem (vía MERGE) |
| `transportEvent.transportTags`    | `object`       | `DrivingInsightsTrip`   | `transport_tags_json`              | Serializado VARBINARY(MAX) |
| `transportEvent.transportTags`    | `object`       | `Trip`                  | `transport_tags_json`              | Idem (vía MERGE) |
| `transportEvent.isProvisional`    | `boolean`      | `Trip`                  | `is_provisional`                   | Para `DrivingInsights`, siempre `false` (evento final) |
| `transportEvent.waypoints`        | `Waypoint[]`   | `Trip`                  | `waypoints_json`                   | Único punto de almacenamiento de coordenadas. Serializado VARBINARY(MAX). |
| `transportEvent.waypoints`        | `Waypoint[]`   | `DrivingInsightsTrip`   | *(campo omitido)*                  | `[omitido]` Para evitar duplicación masiva de datos GPS. |

#### 1.2.1. Sub-estructura: `transportEvent.waypoints[]` (Waypoint)

Almacenados comprimidos en `Trip.waypoints_json` como array JSON:

| Campo JSON (SDK)              | Tipo SDK  | Tabla destino | Columna destino  | Notas |
| ----------------------------- | --------- | ------------- | ---------------- | ----- |
| `latitude`                    | `number`  | `Trip`        | `waypoints_json` | Dentro del array serializado |
| `longitude`                   | `number`  | `Trip`        | `waypoints_json` | Dentro del array serializado |
| `accuracy`                    | `number`  | `Trip`        | `waypoints_json` | En metros |
| `timestamp`                   | `number`  | `Trip`        | `waypoints_json` | UTC epoch en ms |
| `speedInMps`                  | `number?` | `Trip`        | `waypoints_json` | En m/s; opcional |
| `speedLimitInMps`             | `number?` | `Trip`        | `waypoints_json` | En m/s; `undefined` si `isSpeedLimitInfoSet=false` |
| `hasUnlimitedSpeedLimit`      | `boolean` | `Trip`        | `waypoints_json` | `true` si la vía no tiene límite |
| `isSpeedLimitInfoSet`         | `boolean` | `Trip`        | `waypoints_json` | `false` si no hay datos de velocidad máxima |
| `isSynthetic`                 | `boolean` | `Trip`        | `waypoints_json` | `true` si el punto fue interpolado por el SDK |

### 1.3. Sub-estructura: `safetyScores` (SafetyScores)

| Campo JSON (SDK)                    | Tipo SDK   | Tabla destino         | Columna destino              | Notas |
| ----------------------------------- | ---------- | --------------------- | ---------------------------- | ----- |
| `safetyScores.smoothScore`          | `number?`  | `DrivingInsightsTrip` | `smooth_score`               | Rango [0,1]; 1 = perfecto |
| `safetyScores.focusScore`           | `number?`  | `DrivingInsightsTrip` | `focus_score`                | Rango [0,1]; 1 = perfecto |
| `safetyScores.legalScore`           | `number?`  | `DrivingInsightsTrip` | `legal_score`                | Rango [0,1]; 1 = perfecto |
| `safetyScores.callWhileMovingScore` | `number?`  | `DrivingInsightsTrip` | `call_while_moving_score`    | Rango [0,1]; 1 = perfecto |
| `safetyScores.overallScore`         | `number?`  | `DrivingInsightsTrip` | `overall_score`              | Rango [0,1]; 1 = perfecto |
| `safetyScores.harshBrakingScore`    | `number?`  | `DrivingInsightsTrip` | `harsh_braking_score`        | Rango [0,1]; 1 = perfecto |
| `safetyScores.harshTurningScore`    | `number?`  | `DrivingInsightsTrip` | `harsh_turning_score`        | Rango [0,1]; 1 = perfecto |
| `safetyScores.harshAccelerationScore` | `number?`| `DrivingInsightsTrip` | `harsh_acceleration_score`   | Rango [0,1]; 1 = perfecto |
| `safetyScores.wrongWayDrivingScore` | `number?`  | `DrivingInsightsTrip` | `wrong_way_driving_score`    | Rango [0,1]; 1 = perfecto |
| `safetyScores.attentionScore`       | `number?`  | `DrivingInsightsTrip` | `attention_score`            | Rango [0,1]; 1 = perfecto |

---

## 2. `DrivingInsightsHarshEvents`

**Tipo en producción:** `DrivingInsightsHarshEvents`
**Listener SDK:** Llamada auxiliar `getHarshDrivingEvents(transportId)` incluida en el payload de `DrivingInsights`.
**Tabla destino principal:** `DrivingInsightsHarshEvent`

### 2.1. Campos del array `harshDrivingEvents[]` (HarshDrivingEvent)

Cada elemento del array genera **una fila** en `DrivingInsightsHarshEvent`.

| Campo JSON (SDK)    | Tipo SDK              | Tabla destino            | Columna destino            | Notas |
| ------------------- | --------------------- | ------------------------ | -------------------------- | ----- |
| *(registro crudo)*  | —                     | `SentianceEventos`       | `json`                     | Payload completo almacenado antes de procesar |
| *(tipo)*            | —                     | `SentianceEventos`       | `tipo`                     | Valor: `"DrivingInsightsHarshEvents"` |
| *(vínculo)*         | —                     | `DrivingInsightsHarshEvent` | `source_event_id`       | FK → `SdkSourceEvent.source_event_id` |
| *(vínculo)*         | —                     | `DrivingInsightsHarshEvent` | `driving_insights_trip_id` | FK → `DrivingInsightsTrip.driving_insights_trip_id` |
| `startTime`         | `string`              | `DrivingInsightsHarshEvent` | `start_time`            | ISO 8601 |
| `startTimeEpoch`    | `number`              | `DrivingInsightsHarshEvent` | `start_time_epoch`      | UTC en ms |
| `endTime`           | `string`              | `DrivingInsightsHarshEvent` | `end_time`              | ISO 8601 |
| `endTimeEpoch`      | `number`              | `DrivingInsightsHarshEvent` | `end_time_epoch`        | UTC en ms |
| `magnitude`         | `number`              | `DrivingInsightsHarshEvent` | `magnitude`             | Fuerza G máxima detectada |
| `confidence`        | `number`              | `DrivingInsightsHarshEvent` | `confidence`            | Confianza [0,1] |
| `type`              | `HarshDrivingEventType` | `DrivingInsightsHarshEvent` | `harsh_type`          | `"ACCELERATION"`, `"BRAKING"`, `"TURN"` |
| `waypoints`         | `Waypoint[]`          | `DrivingInsightsHarshEvent` | `waypoints_json`        | Array serializado VARBINARY(MAX) |

#### 2.1.1. Sub-estructura: `waypoints[]` (Waypoint) dentro de HarshDrivingEvent

| Campo JSON (SDK)         | Tipo SDK  | Tabla destino               | Columna destino  | Notas |
| ------------------------ | --------- | --------------------------- | ---------------- | ----- |
| `latitude`               | `number`  | `DrivingInsightsHarshEvent` | `waypoints_json` | Dentro del array serializado |
| `longitude`              | `number`  | `DrivingInsightsHarshEvent` | `waypoints_json` | Dentro del array serializado |
| `accuracy`               | `number`  | `DrivingInsightsHarshEvent` | `waypoints_json` | En metros |
| `timestamp`              | `number`  | `DrivingInsightsHarshEvent` | `waypoints_json` | UTC epoch en ms |
| `speedInMps`             | `number?` | `DrivingInsightsHarshEvent` | `waypoints_json` | En m/s; opcional |
| `speedLimitInMps`        | `number?` | `DrivingInsightsHarshEvent` | `waypoints_json` | En m/s; opcional |
| `hasUnlimitedSpeedLimit` | `boolean` | `DrivingInsightsHarshEvent` | `waypoints_json` | — |
| `isSpeedLimitInfoSet`    | `boolean` | `DrivingInsightsHarshEvent` | `waypoints_json` | — |
| `isSynthetic`            | `boolean` | `DrivingInsightsHarshEvent` | `waypoints_json` | — |

---

## 3. `DrivingInsightsPhoneEvents`

**Tipo en producción:** `DrivingInsightsPhoneEvents`
**Listener SDK:** Llamada auxiliar `getPhoneUsageEvents(transportId)` incluida en el payload.
**Tabla destino principal:** `DrivingInsightsPhoneEvent`

### 3.1. Campos del array `phoneUsageEvents[]` (PhoneUsageEvent)

Cada elemento del array genera **una fila** en `DrivingInsightsPhoneEvent`.

| Campo JSON (SDK)    | Tipo SDK          | Tabla destino              | Columna destino            | Notas |
| ------------------- | ----------------- | -------------------------- | -------------------------- | ----- |
| *(registro crudo)*  | —                 | `SentianceEventos`         | `json`                     | Payload completo |
| *(tipo)*            | —                 | `SentianceEventos`         | `tipo`                     | Valor: `"DrivingInsightsPhoneEvents"` |
| *(vínculo)*         | —                 | `DrivingInsightsPhoneEvent` | `source_event_id`         | FK → `SdkSourceEvent.source_event_id` |
| *(vínculo)*         | —                 | `DrivingInsightsPhoneEvent` | `driving_insights_trip_id` | FK → `DrivingInsightsTrip.driving_insights_trip_id` |
| `startTime`         | `string`          | `DrivingInsightsPhoneEvent` | `start_time`              | ISO 8601 |
| `startTimeEpoch`    | `number`          | `DrivingInsightsPhoneEvent` | `start_time_epoch`        | UTC en ms |
| `endTime`           | `string`          | `DrivingInsightsPhoneEvent` | `end_time`                | ISO 8601 |
| `endTimeEpoch`      | `number`          | `DrivingInsightsPhoneEvent` | `end_time_epoch`          | UTC en ms |
| `callState`         | `string`          | `DrivingInsightsPhoneEvent` | *(no mapeado)*            | `[omitido]` `"NO_CALL"`, `"CALL_IN_PROGRESS"`, `"UNAVAILABLE"` — no tiene columna dedicada en el esquema actual |
| `waypoints`         | `Waypoint[]`      | `DrivingInsightsPhoneEvent` | `waypoints_json`          | Array serializado VARBINARY(MAX) |

> **⚠️ GAP identificado:** El campo `callState` (`"NO_CALL"` | `"CALL_IN_PROGRESS"` | `"UNAVAILABLE"`) de `PhoneUsageEvent` no tiene columna dedicada en `DrivingInsightsPhoneEvent`. Se recomienda agregar `call_state VARCHAR(32)`.

#### 3.1.1. Sub-estructura: `waypoints[]` dentro de PhoneUsageEvent

| Campo JSON (SDK)         | Tipo SDK  | Tabla destino               | Columna destino  | Notas |
| ------------------------ | --------- | --------------------------- | ---------------- | ----- |
| `latitude`               | `number`  | `DrivingInsightsPhoneEvent` | `waypoints_json` | Dentro del array serializado |
| `longitude`              | `number`  | `DrivingInsightsPhoneEvent` | `waypoints_json` | — |
| `accuracy`               | `number`  | `DrivingInsightsPhoneEvent` | `waypoints_json` | En metros |
| `timestamp`              | `number`  | `DrivingInsightsPhoneEvent` | `waypoints_json` | UTC epoch en ms |
| `speedInMps`             | `number?` | `DrivingInsightsPhoneEvent` | `waypoints_json` | Opcional |
| `speedLimitInMps`        | `number?` | `DrivingInsightsPhoneEvent` | `waypoints_json` | Opcional |
| `hasUnlimitedSpeedLimit` | `boolean` | `DrivingInsightsPhoneEvent` | `waypoints_json` | — |
| `isSpeedLimitInfoSet`    | `boolean` | `DrivingInsightsPhoneEvent` | `waypoints_json` | — |
| `isSynthetic`            | `boolean` | `DrivingInsightsPhoneEvent` | `waypoints_json` | — |

---

## 4. `DrivingInsightsCallEvents`

**Tipo en producción:** `DrivingInsightsCallEvents`
**Listener SDK:** Llamada auxiliar `getCallEvents(transportId)` (reemplaza al deprecado `getCallWhileMovingEvents`).
**Tabla destino principal:** `DrivingInsightsCallEvent`

### 4.1. Campos del array `callEvents[]` (CallEvent)

Cada elemento del array genera **una fila** en `DrivingInsightsCallEvent`.

| Campo JSON (SDK)             | Tipo SDK        | Tabla destino              | Columna destino              | Notas |
| ---------------------------- | --------------- | -------------------------- | ---------------------------- | ----- |
| *(registro crudo)*           | —               | `SentianceEventos`         | `json`                       | Payload completo |
| *(tipo)*                     | —               | `SentianceEventos`         | `tipo`                       | Valor: `"DrivingInsightsCallEvents"` |
| *(vínculo)*                  | —               | `DrivingInsightsCallEvent` | `source_event_id`            | FK → `SdkSourceEvent.source_event_id` |
| *(vínculo)*                  | —               | `DrivingInsightsCallEvent` | `driving_insights_trip_id`   | FK → `DrivingInsightsTrip.driving_insights_trip_id` |
| `startTime`                  | `string`        | `DrivingInsightsCallEvent` | `start_time`                 | ISO 8601 |
| `startTimeEpoch`             | `number`        | `DrivingInsightsCallEvent` | `start_time_epoch`           | UTC en ms |
| `endTime`                    | `string`        | `DrivingInsightsCallEvent` | `end_time`                   | ISO 8601 |
| `endTimeEpoch`               | `number`        | `DrivingInsightsCallEvent` | `end_time_epoch`             | UTC en ms |
| `minTraveledSpeedInMps`      | `number\|null`  | `DrivingInsightsCallEvent` | `min_travelled_speed_mps`    | Velocidad mínima en m/s durante la llamada |
| `maxTraveledSpeedInMps`      | `number\|null`  | `DrivingInsightsCallEvent` | `max_travelled_speed_mps`    | Velocidad máxima en m/s durante la llamada |
| `handsFreeState`             | `string`        | `DrivingInsightsCallEvent` | *(no mapeado)*               | `[omitido]` `"HANDS_FREE"` / `"HANDHELD"` / `"UNAVAILABLE"` — sin columna en el esquema actual |
| `waypoints`                  | `Waypoint[]`    | `DrivingInsightsCallEvent` | `waypoints_json`             | Array serializado VARBINARY(MAX) |

> **⚠️ GAP identificado:** El campo `handsFreeState` de `CallEvent` no tiene columna en `DrivingInsightsCallEvent`. Se recomienda agregar `hands_free_state VARCHAR(32)`.

#### 4.1.1. Sub-estructura: `waypoints[]` dentro de CallEvent

*(Estructura idéntica a la sección 2.1.1 — mismo modelo `Waypoint`; almacenado en `DrivingInsightsCallEvent.waypoints_json`)*

---

## 5. `DrivingInsightsSpeedingEvents`

**Tipo en producción:** `DrivingInsightsSpeedingEvents`
**Listener SDK:** Llamada auxiliar `getSpeedingEvents(transportId)`.
**Tabla destino principal:** `DrivingInsightsSpeedingEvent`

### 5.1. Campos del array `speedingEvents[]` (SpeedingEvent)

Cada elemento del array genera **una fila** en `DrivingInsightsSpeedingEvent`.

| Campo JSON (SDK)    | Tipo SDK     | Tabla destino                | Columna destino            | Notas |
| ------------------- | ------------ | ---------------------------- | -------------------------- | ----- |
| *(registro crudo)*  | —            | `SentianceEventos`           | `json`                     | Payload completo |
| *(tipo)*            | —            | `SentianceEventos`           | `tipo`                     | Valor: `"DrivingInsightsSpeedingEvents"` |
| *(vínculo)*         | —            | `DrivingInsightsSpeedingEvent` | `source_event_id`        | FK → `SdkSourceEvent.source_event_id` |
| *(vínculo)*         | —            | `DrivingInsightsSpeedingEvent` | `driving_insights_trip_id` | FK → `DrivingInsightsTrip.driving_insights_trip_id` |
| `startTime`         | `string`     | `DrivingInsightsSpeedingEvent` | `start_time`             | ISO 8601 |
| `startTimeEpoch`    | `number`     | `DrivingInsightsSpeedingEvent` | `start_time_epoch`       | UTC en ms |
| `endTime`           | `string`     | `DrivingInsightsSpeedingEvent` | `end_time`               | ISO 8601 |
| `endTimeEpoch`      | `number`     | `DrivingInsightsSpeedingEvent` | `end_time_epoch`         | UTC en ms |
| `waypoints`         | `Waypoint[]` | `DrivingInsightsSpeedingEvent` | `waypoints_json`         | Array serializado VARBINARY(MAX) |

#### 5.1.1. Sub-estructura: `waypoints[]` dentro de SpeedingEvent

*(Estructura idéntica a la sección 2.1.1 — mismo modelo `Waypoint`; almacenado en `DrivingInsightsSpeedingEvent.waypoints_json`)*

---

## 6. `DrivingInsightsWrongWayDrivingEvents`

**Tipo en producción:** `DrivingInsightsWrongWayDrivingEvents`
**Listener SDK:** Llamada auxiliar `getWrongWayDrivingEvents(transportId)`.
**Tabla destino principal:** `DrivingInsightsWrongWayDrivingEvent`

### 6.1. Campos del array `wrongWayDrivingEvents[]` (WrongWayDrivingEvent)

Cada elemento del array genera **una fila** en `DrivingInsightsWrongWayDrivingEvent`.

| Campo JSON (SDK)    | Tipo SDK     | Tabla destino                        | Columna destino            | Notas |
| ------------------- | ------------ | ------------------------------------ | -------------------------- | ----- |
| *(registro crudo)*  | —            | `SentianceEventos`                   | `json`                     | Payload completo |
| *(tipo)*            | —            | `SentianceEventos`                   | `tipo`                     | Valor: `"DrivingInsightsWrongWayDrivingEvents"` |
| *(vínculo)*         | —            | `DrivingInsightsWrongWayDrivingEvent` | `source_event_id`         | FK → `SdkSourceEvent.source_event_id` |
| *(vínculo)*         | —            | `DrivingInsightsWrongWayDrivingEvent` | `driving_insights_trip_id` | FK → `DrivingInsightsTrip.driving_insights_trip_id` |
| `startTime`         | `string`     | `DrivingInsightsWrongWayDrivingEvent` | `start_time`              | ISO 8601 |
| `startTimeEpoch`    | `number`     | `DrivingInsightsWrongWayDrivingEvent` | `start_time_epoch`        | UTC en ms |
| `endTime`           | `string`     | `DrivingInsightsWrongWayDrivingEvent` | `end_time`                | ISO 8601 |
| `endTimeEpoch`      | `number`     | `DrivingInsightsWrongWayDrivingEvent` | `end_time_epoch`          | UTC en ms |
| `waypoints`         | `Waypoint[]` | `DrivingInsightsWrongWayDrivingEvent` | `waypoints_json`          | Array serializado VARBINARY(MAX) |

#### 6.1.1. Sub-estructura: `waypoints[]` dentro de WrongWayDrivingEvent

*(Estructura idéntica a la sección 2.1.1 — mismo modelo `Waypoint`; almacenado en `DrivingInsightsWrongWayDrivingEvent.waypoints_json`)*

---

## 7. `UserContextUpdate`

**Tipo en producción:** `UserContextUpdate`
**Listener SDK:** `addUserContextUpdateListener` — emite un `UserContextUpdate` (con wrapper).
**Ref. SDK:** `@sentiance-react-native/user-context` — [Definitions](https://docs.sentiance.com/important-topics/sdk/api-reference/react-native/user-context/definitions)

El payload raíz es `UserContextUpdate`, que contiene:
- `criteria`: Array de strings indicando qué cambió.
- `userContext`: El contexto completo del usuario.

### 7.1. Payload raíz (`UserContextUpdate`)

| Campo JSON (SDK)  | Tipo SDK                      | Tabla destino               | Columna destino          | Notas |
| ----------------- | ----------------------------- | --------------------------- | ------------------------ | ----- |
| *(registro crudo)*| —                             | `SentianceEventos`          | `json`                   | Payload completo |
| *(tipo)*          | —                             | `SentianceEventos`          | `tipo`                   | Valor: `"UserContextUpdate"` |
| `criteria[]`      | `UserContextUpdateCriteria[]` | `UserContextUpdateCriteria` | `criteria_code`          | 1 fila por elemento. Valores: `"CURRENT_EVENT"`, `"ACTIVE_SEGMENTS"`, `"VISITED_VENUES"` |

### 7.2. Sub-estructura: `userContext` (UserContext)

#### 7.2.1. Campos escalares de `UserContext`

| Campo JSON (SDK)                      | Tipo SDK        | Tabla destino      | Columna destino         | Notas |
| ------------------------------------- | --------------- | ------------------ | ----------------------- | ----- |
| `userContext.semanticTime`            | `SemanticTime`  | `UserContextHeader` | `semantic_time`        | `"MORNING"`, `"LUNCH"`, `"NIGHT"`, etc. |
| `userContext.lastKnownLocation.latitude` | `number`     | `UserContextHeader` | `last_known_latitude`  | Coordenada Y |
| `userContext.lastKnownLocation.longitude` | `number`    | `UserContextHeader` | `last_known_longitude` | Coordenada X |
| `userContext.lastKnownLocation.accuracy` | `number`     | `UserContextHeader` | `last_known_accuracy`  | Precisión en metros |

#### 7.2.2. Sub-estructura: `userContext.home` y `userContext.work` (Venue)

| Campo JSON (SDK)              | Tipo SDK          | Tabla destino      | Columna destino    | Notas |
| ----------------------------- | ----------------- | ------------------ | ------------------ | ----- |
| `userContext.home.significance` | `VenueSignificance` | `UserHomeHistory` | `significance`  | Siempre `"HOME"` |
| `userContext.home.type`         | `VenueType`         | `UserHomeHistory` | `venue_type`    | p.ej. `"RESIDENTIAL"` |
| `userContext.home.location.latitude` | `number`       | `UserHomeHistory` | `latitude`      | — |
| `userContext.home.location.longitude` | `number`      | `UserHomeHistory` | `longitude`     | — |
| `userContext.home.location.accuracy` | `number`       | `UserHomeHistory` | `accuracy`      | En metros |
| `userContext.work.significance` | `VenueSignificance` | `UserWorkHistory` | `significance`  | Siempre `"WORK"` |
| `userContext.work.type`         | `VenueType`         | `UserWorkHistory` | `venue_type`    | p.ej. `"OFFICE"` |
| `userContext.work.location.latitude` | `number`       | `UserWorkHistory` | `latitude`      | — |
| `userContext.work.location.longitude` | `number`      | `UserWorkHistory` | `longitude`     | — |
| `userContext.work.location.accuracy` | `number`       | `UserWorkHistory` | `accuracy`      | En metros |

#### 7.2.3. Sub-estructura: `userContext.activeSegments[]` (Segment)

Cada elemento del array genera **una fila** en `UserContextActiveSegmentDetail`.

| Campo JSON (SDK)                    | Tipo SDK              | Tabla destino                    | Columna destino              | Notas |
| ----------------------------------- | --------------------- | -------------------------------- | ---------------------------- | ----- |
| `id`                                | `number`              | `UserContextActiveSegmentDetail` | `segment_id`                 | ID del segmento Sentiance |
| `category`                          | `SegmentCategory`     | `UserContextActiveSegmentDetail` | `category`                   | `"LEISURE"`, `"MOBILITY"`, `"WORK_LIFE"` |
| `subcategory`                       | `SegmentSubcategory`  | `UserContextActiveSegmentDetail` | `subcategory`                | p.ej. `"DRIVING"`, `"SHOPPING"` |
| `type`                              | `SegmentType`         | `UserContextActiveSegmentDetail` | `segment_type`               | p.ej. `"CITY_WORKER"`, `"EARLY_BIRD"` |
| `startTime`                         | `string`              | `UserContextActiveSegmentDetail` | `start_time`                 | ISO 8601 |
| `startTimeEpoch`                    | `number`              | `UserContextActiveSegmentDetail` | `start_time_epoch`           | UTC en ms |
| `endTime`                           | `string\|null`        | `UserContextActiveSegmentDetail` | `end_time`                   | ISO 8601; null si está activo |
| `endTimeEpoch`                      | `number\|null`        | `UserContextActiveSegmentDetail` | `end_time_epoch`             | UTC en ms |

##### 7.2.3.1. Sub-estructura: `segment.attributes[]` (SegmentAttribute)

Cada elemento del sub-array genera **una fila** en `UserContextSegmentAttribute`.

| Campo JSON (SDK) | Tipo SDK | Tabla destino                  | Columna destino         | Notas |
| ---------------- | -------- | ------------------------------ | ----------------------- | ----- |
| `name`           | `string` | `UserContextSegmentAttribute`  | `attribute_name`        | p.ej. `"home_time"`, `"arrival_time_weekday"` |
| `value`          | `number` | `UserContextSegmentAttribute`  | `attribute_value`       | Valor numérico del atributo |

#### 7.2.4. Sub-estructura: `userContext.events[]` (Event)

Cada elemento del array genera **una fila** en `UserContextEventDetail`.

| Campo JSON (SDK)       | Tipo SDK              | Tabla destino            | Columna destino         | Notas |
| ---------------------- | --------------------- | ------------------------ | ----------------------- | ----- |
| `id`                   | `string`              | `UserContextEventDetail` | `event_id`              | ID del evento Sentiance |
| `type`                 | `string`              | `UserContextEventDetail` | `event_type`            | `"STATIONARY"`, `"IN_TRANSPORT"`, `"OFF_THE_GRID"`, `"UNKNOWN"` |
| `startTime`            | `string`              | `UserContextEventDetail` | `start_time`            | ISO 8601 |
| `startTimeEpoch`       | `number`              | `UserContextEventDetail` | `start_time_epoch`      | UTC en ms |
| `lastUpdateTime`       | `string`              | `UserContextEventDetail` | `last_update_time`      | ISO 8601 |
| `lastUpdateTimeEpoch`  | `number`              | `UserContextEventDetail` | `last_update_time_epoch`| UTC en ms |
| `endTime`              | `string\|null`        | `UserContextEventDetail` | `end_time`              | ISO 8601 |
| `endTimeEpoch`         | `number\|null`        | `UserContextEventDetail` | `end_time_epoch`        | UTC en ms |
| `durationInSeconds`    | `number\|null`        | `UserContextEventDetail` | `duration_in_seconds`   | — |
| `isProvisional`        | `boolean`             | `UserContextEventDetail` | `is_provisional`        | — |
| `transportMode`        | `TransportMode\|null` | `UserContextEventDetail` | `transport_mode`        | Solo para `IN_TRANSPORT` |
| `distance`             | `number?`             | `UserContextEventDetail` | `distance_meters`       | En metros; solo para `IN_TRANSPORT` |
| `occupantRole`         | `OccupantRole`        | `UserContextEventDetail` | `occupant_role`         | `"DRIVER"`, `"PASSENGER"`, `"UNAVAILABLE"` |
| `transportTags`        | `object`              | `UserContextEventDetail` | `transport_tags_json`   | Serializado VARBINARY(MAX) |
| `location.latitude`    | `number\|null`        | `UserContextEventDetail` | `location_latitude`     | Solo para `STATIONARY` |
| `location.longitude`   | `number\|null`        | `UserContextEventDetail` | `location_longitude`    | Solo para `STATIONARY` |
| `location.accuracy`    | `number\|null`        | `UserContextEventDetail` | `location_accuracy`     | Solo para `STATIONARY` |
| `venue.significance`   | `VenueSignificance\|null` | `UserContextEventDetail` | `venue_significance` | Solo para `STATIONARY` |
| `venue.type`           | `VenueType\|null`     | `UserContextEventDetail` | `venue_type`            | Solo para `STATIONARY` |
| `waypoints`            | `Waypoint[]`          | `UserContextEventDetail` | *(omitido)*             | `[omitido]` Se almacena en `Trip.waypoints_json` para evitar duplicación. |

---

## 8. `requestUserContext`

**Tipo en producción:** `requestUserContext`
**Origen SDK:** Llamada manual `SentianceUserContext.requestUserContext()` desde la App.
**Diferencia estructural clave:** El payload es un objeto `UserContext` **plano** (sin el wrapper `userContext` ni el campo `criteria`).
**Tablas destino:** **Las mismas que `UserContextUpdate`** (sección 7), con las siguientes diferencias:

| Característica           | `UserContextUpdate`          | `requestUserContext`                          |
| ------------------------ | ---------------------------- | --------------------------------------------- |
| Extracción del contexto  | `json["userContext"]`        | `json` directamente (es el UserContext plano) |
| Campo `criteria`         | `json["criteria"][]`         | `[sintético]` valor fijo: `"MANUAL_REQUEST"`  |
| `UserContextUpdateCriteria.criteria_code` | Del payload | Siempre `"MANUAL_REQUEST"` |

### 8.1. Mapeo de campos

El mapeo es **idéntico al de la sección 7** (`UserContextUpdate`), exceptuando:

| Campo JSON (SDK)    | Tabla destino               | Columna destino  | Notas |
| ------------------- | --------------------------- | ---------------- | ----- |
| *(no existe)*       | `UserContextUpdateCriteria` | `criteria_code`  | `[sintético]` El ETL inserta `"MANUAL_REQUEST"` (decisión arquitectónica Opción A). |
| `semanticTime`      | `UserContextHeader`         | `semantic_time`  | En `requestUserContext`, el campo está en la raíz del JSON, no dentro de `userContext`. |

> Todos los demás campos siguen el mismo mapeo que `UserContextUpdate` (sección 7.2).

---

## 9. `TimelineEvents`

**Tipo en producción:** `TimelineEvents`
**Equivalente SDK:** `TimelineUpdate` (listener `addTimelineUpdateListener`)
**Ref. SDK:** `@sentiance-react-native/event-timeline`
**Tabla destino principal:** `TimelineEventHistory`

El payload es un **array de objetos `Event`**. Cada elemento genera **una fila** en `TimelineEventHistory`.

### 9.1. Campos de cada `Event[]`

| Campo JSON (SDK)       | Tipo SDK              | Tabla destino          | Columna destino          | Notas |
| ---------------------- | --------------------- | ---------------------- | ------------------------ | ----- |
| *(registro crudo)*     | —                     | `SentianceEventos`     | `json`                   | Payload completo (array de eventos) |
| *(tipo)*               | —                     | `SentianceEventos`     | `tipo`                   | Valor: `"TimelineEvents"` |
| *(vínculo)*            | —                     | `TimelineEventHistory` | `source_event_id`        | FK → `SdkSourceEvent.source_event_id` |
| `id`                   | `string`              | `TimelineEventHistory` | `event_id`               | Si `type = "IN_TRANSPORT"`, coincide con `Trip.canonical_transport_event_id` |
| `type`                 | `EventType`           | `TimelineEventHistory` | `event_type`             | `"UNKNOWN"`, `"STATIONARY"`, `"OFF_THE_GRID"`, `"IN_TRANSPORT"` |
| `startTime`            | `string`              | `TimelineEventHistory` | `start_time`             | ISO 8601 |
| `startTimeEpoch`       | `number`              | `TimelineEventHistory` | `start_time_epoch`       | UTC en ms |
| `lastUpdateTime`       | `string`              | `TimelineEventHistory` | `last_update_time`       | ISO 8601 |
| `lastUpdateTimeEpoch`  | `number`              | `TimelineEventHistory` | `last_update_time_epoch` | UTC en ms |
| `endTime`              | `string\|null`        | `TimelineEventHistory` | `end_time`               | ISO 8601 |
| `endTimeEpoch`         | `number\|null`        | `TimelineEventHistory` | `end_time_epoch`         | UTC en ms |
| `durationInSeconds`    | `number\|null`        | `TimelineEventHistory` | `duration_in_seconds`    | — |
| `isProvisional`        | `boolean`             | `TimelineEventHistory` | `is_provisional`         | `true` si el evento puede cambiar |
| `transportMode`        | `TransportMode\|null` | `TimelineEventHistory` | `transport_mode`         | Solo para `IN_TRANSPORT` |
| `distance`             | `number?`             | `TimelineEventHistory` | `distance_meters`        | En metros; solo para `IN_TRANSPORT` |
| `occupantRole`         | `OccupantRole`        | `TimelineEventHistory` | `occupant_role`          | — |
| `transportTags`        | `object`              | `TimelineEventHistory` | `transport_tags_json`    | Serializado VARBINARY(MAX) |
| `location.latitude`    | `number\|null`        | `TimelineEventHistory` | `location_latitude`      | Solo para `STATIONARY` |
| `location.longitude`   | `number\|null`        | `TimelineEventHistory` | `location_longitude`     | Solo para `STATIONARY` |
| `location.accuracy`    | `number\|null`        | `TimelineEventHistory` | `location_accuracy`      | Solo para `STATIONARY` |
| `venue.significance`   | `VenueSignificance\|null` | `TimelineEventHistory` | `venue_significance` | Solo para `STATIONARY` |
| `venue.type`           | `VenueType\|null`     | `TimelineEventHistory` | `venue_type`             | Solo para `STATIONARY` |
| `waypoints`            | `Waypoint[]`          | `Trip`                 | `waypoints_json`         | Si `type = "IN_TRANSPORT"`, los waypoints se almacenan en `Trip` vía MERGE. |

#### 9.1.1. Sub-estructura: `waypoints[]` (Event de tipo IN_TRANSPORT)

*(Estructura idéntica a la sección 1.2.1 — mismo modelo `Waypoint`; se almacena en `Trip.waypoints_json` vía MERGE usando `event.id` como clave de deduplicación)*

---

## 10. `SDKStatus`

**Tipo en producción:** `SDKStatus`
**Equivalente SDK:** `SdkStatus` (listener `addSdkStatusUpdateListener`)
**Ref. SDK:** [SdkStatus API Reference](https://docs.sentiance.com/important-topics/sdk/api-reference/android/sdkstatus)
**Tabla destino principal:** `SdkStatusHistory`

> **Nota de captura parcial:** La interfaz `SdkStatus` del SDK expone decenas de propiedades. El esquema almacena solo un subconjunto relevante para monitoreo operativo.

### 10.1. Campos del objeto `SdkStatus`

| Campo JSON (SDK)                    | Tipo SDK          | Tabla destino      | Columna destino            | ¿Almacenado? | Notas |
| ----------------------------------- | ----------------- | ------------------ | -------------------------- | ------------ | ----- |
| *(registro crudo)*                  | —                 | `SentianceEventos` | `json`                     | ✅ | Payload completo |
| *(tipo)*                            | —                 | `SentianceEventos` | `tipo`                     | ✅ | Valor: `"SDKStatus"` |
| `detectionStatus`                   | `DetectionStatus` | `SdkStatusHistory` | `detection_status`         | ✅ | `"DISABLED"`, `"ENABLED"`, `"EXPIRED"`, etc. |
| `startStatus` *(deprecated)*        | `StartStatus`     | `SdkStatusHistory` | `start_status`             | ✅ | Mantenido por compatibilidad; usar `detectionStatus` |
| `canDetect`                         | `boolean`         | `SdkStatusHistory` | `can_detect`               | ✅ | Síntesis de múltiples condiciones |
| `isRemoteEnabled`                   | `boolean`         | `SdkStatusHistory` | *(no mapeado)*             | ❌ | `[omitido]` |
| `isPreciseLocationPermGranted`      | `boolean`         | `SdkStatusHistory` | `precise_location_granted` | ✅ | — |
| `isActivityRecognitionPermGranted`  | `boolean`         | `SdkStatusHistory` | *(no mapeado)*             | ❌ | `[omitido]` |
| `locationSetting`                   | `LocationSetting` | `SdkStatusHistory` | *(no mapeado)*             | ❌ | `[omitido]` |
| `isAirplaneModeEnabled`             | `boolean`         | `SdkStatusHistory` | *(no mapeado)*             | ❌ | `[omitido]` |
| `isLocationAvailable`               | `boolean`         | `SdkStatusHistory` | `is_location_available`    | ✅ | — |
| `isAccelPresent`                    | `boolean`         | `SdkStatusHistory` | *(no mapeado)*             | ❌ | `[omitido]` |
| `isGyroPresent`                     | `boolean`         | `SdkStatusHistory` | *(no mapeado)*             | ❌ | `[omitido]` |
| `isGpsPresent`                      | `boolean`         | `SdkStatusHistory` | *(no mapeado)*             | ❌ | `[omitido]` |
| `isGooglePlayServicesMissing`       | `boolean`         | `SdkStatusHistory` | *(no mapeado)*             | ❌ | `[omitido]` |
| `isBatteryOptimizationEnabled`      | `boolean`         | `SdkStatusHistory` | *(no mapeado)*             | ❌ | `[omitido]` |
| `isBatterySavingEnabled`            | `boolean`         | `SdkStatusHistory` | *(no mapeado)*             | ❌ | `[omitido]` |
| `isBackgroundProcessingRestricted`  | `boolean`         | `SdkStatusHistory` | *(no mapeado)*             | ❌ | `[omitido]` |
| `isSchedulingExactAlarmsPermitted`  | `boolean`         | `SdkStatusHistory` | *(no mapeado)*             | ❌ | `[omitido]` |
| `locationPermission`                | `LocationPermission` | `SdkStatusHistory` | `location_permission`   | ✅ | `"ALWAYS"`, `"WHILE_IN_USE"`, `"NEVER"` |
| `wifiQuotaStatus`                   | `QuotaStatus`     | `SdkStatusHistory` | `quota_status_wifi`        | ✅ | `"OK"`, `"WARNING"`, `"EXCEEDED"` |
| `mobileQuotaStatus`                 | `QuotaStatus`     | `SdkStatusHistory` | `quota_status_mobile`      | ✅ | `"OK"`, `"WARNING"`, `"EXCEEDED"` |
| `diskQuotaStatus`                   | `QuotaStatus`     | `SdkStatusHistory` | `quota_status_disk`        | ✅ | `"OK"`, `"WARNING"`, `"EXCEEDED"` |

---

## 11. `VehicleCrash`

**Tipo en producción:** `VehicleCrash`
**Equivalente SDK:** `CrashEvent` (listener `addVehicleCrashEventListener`)
**Ref. SDK:** `@sentiance-react-native/crash-detection`
**Tabla destino principal:** `VehicleCrashEvent`

### 11.1. Campos del objeto `CrashEvent`

| Campo JSON (SDK)          | Tipo SDK          | Tabla destino      | Columna destino              | Notas |
| ------------------------- | ----------------- | ------------------ | ---------------------------- | ----- |
| *(registro crudo)*        | —                 | `SentianceEventos` | `json`                       | Payload completo |
| *(tipo)*                  | —                 | `SentianceEventos` | `tipo`                       | Valor: `"VehicleCrash"` |
| *(vínculo)*               | —                 | `VehicleCrashEvent` | `source_event_id`           | FK → `SdkSourceEvent.source_event_id` |
| `time`                    | `number`          | `VehicleCrashEvent` | `crash_time_epoch`          | UTC epoch en ms |
| `location.latitude`       | `number`          | `VehicleCrashEvent` | `latitude`                  | Coordenada Y del impacto |
| `location.longitude`      | `number`          | `VehicleCrashEvent` | `longitude`                 | Coordenada X del impacto |
| `location.accuracy`       | `number`          | `VehicleCrashEvent` | `accuracy`                  | Precisión GPS en metros |
| `location.altitude`       | `number`          | `VehicleCrashEvent` | `altitude`                  | Altitud en metros |
| `magnitude`               | `number`          | `VehicleCrashEvent` | `magnitude`                 | Fuerza G detectada |
| `speedAtImpact`           | `number`          | `VehicleCrashEvent` | `speed_at_impact`           | Velocidad al impacto en m/s |
| `deltaV`                  | `number`          | `VehicleCrashEvent` | `delta_v`                   | Cambio de velocidad en m/s |
| `confidence`              | `number`          | `VehicleCrashEvent` | `confidence`                | Confianza de la detección [0,1] |
| `severity`                | `string`          | `VehicleCrashEvent` | `severity`                  | `"LOW"`, `"MEDIUM"`, `"HIGH"` |
| `detectorMode`            | `string`          | `VehicleCrashEvent` | `detector_mode`             | `"CAR"`, `"DRIVE"` |
| `precedingLocations`      | `GeoLocation[]`   | `VehicleCrashEvent` | `preceding_locations_json`  | Array de ubicaciones previas, serializado VARBINARY(MAX) |

#### 11.1.1. Sub-estructura: `precedingLocations[]` (GeoLocation)

Almacenados comprimidos en `VehicleCrashEvent.preceding_locations_json` como array JSON:

| Campo JSON (SDK) | Tipo SDK | Tabla destino       | Columna destino              | Notas |
| ---------------- | -------- | ------------------- | ---------------------------- | ----- |
| `latitude`       | `number` | `VehicleCrashEvent` | `preceding_locations_json`   | Dentro del array serializado |
| `longitude`      | `number` | `VehicleCrashEvent` | `preceding_locations_json`   | — |
| `accuracy`       | `number` | `VehicleCrashEvent` | `preceding_locations_json`   | En metros |

---

*Fin del documento*
