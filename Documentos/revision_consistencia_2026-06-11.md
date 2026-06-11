# Revisión Integral de Consistencia — Código ↔ Documentación ↔ SDK Sentiance

> **Fecha:** 2026-06-11
> **Alcance:** `etl/`, `scripts/`, `development/`, `tests/`, `README.md`, `CLAUDE.md`,
> `Documentos/*` contrastados entre sí y contra la documentación oficial de Sentiance
> (`scraped_site/wiki/`, ignorando `raw/`), los payloads reales
> (`development/test_small_full.json`, `development/sample_payloads.json.gz` — export de producción)
> y las bases de datos accesibles vía MCP (`mssql` producción RDS; `mssql-movilidad` inalcanzable
> desde esta red, no verificado).
> **Estado del repo al momento de la revisión:** rama `main`, working tree limpio, commit `c05bc3b`.
> **Tests:** 122 passed (`.venv/bin/pytest tests/ -q`).

---

## Resumen Ejecutivo

| Severidad | Cantidad | Hallazgos principales |
|-----------|----------|----------------------|
| 🔴 CRÍTICO | 2 | `TimelineUpdate` se descarta silenciosamente; `SDKStatus` se persiste con todos los campos NULL/0 |
| 🟠 ALTO | 4 | Campos de velocidad en CallEvent siempre NULL; esquema de producción ≠ esquema documentado; escala de `confidence` inconsistente en 3 documentos y el código; `analisis_mapeo_movilidad.md` §10 desactualizado |
| 🟡 MEDIO | 8 | Variante lista de Timeline rompe `run()`; `UserActivity` incompatible con el SDK; CLAUDE.md incompleto/impreciso; conteos de tests desactualizados (94/114 vs 122 reales); múltiples enums erróneos en DiccionarioDatos; errores puntuales en MapeoSDK_BD; deriva diseño-vs-DDL del Entregable; development/README desactualizado |
| 🟢 BAJO | 7 | Detalles menores de diagramas, nombres de columnas en docs, logging, conteo de progreso |

Lo estructural (modelo de 24 tablas, mapeo de SafetyScores, TransportEvent, UserContext,
VehicleCrash, harsh/phone/speeding/wrong-way events, el guard de huérfanos, el bridge Movilidad
y su DDL local) está **bien alineado** entre código, DDL y SDK. Los problemas graves se
concentran en dos tipos de evento cuyos payloads reales no tienen la forma que el código asume
(`TimelineUpdate`, `SDKStatus`) y en afirmaciones de los documentos que ya no reflejan ni el
código ni el SDK.

---

## 1. Hallazgos CRÍTICOS (pérdida/corrupción silenciosa de datos)

### C1. Los eventos `TimelineUpdate` se procesan "exitosamente" pero no insertan nada

- **Payload real** (1.962 de 1.962 registros `TimelineUpdate` en `sample_payloads.json.gz`):
  ```json
  { "source": "catchup", "event": { "id": "...", "type": "STATIONARY", ... } }
  ```
  Un **único** `Event` bajo la clave `event`, consistente con el listener
  `addTimelineUpdateListener` del SDK, que emite **un evento por invocación**
  (`scraped_site/wiki/api-reference/react-native/event-timeline/timeline/definitions.md`).
- **Código:** `process_timeline_events()` (`etl/sentiance_etl.py:700-748`) solo contempla
  `{"events": [...]}` o una lista. Para `TimelineUpdate` hace
  `payload.get("events", [])` → `[]` → **cero filas** en `TimelineEventHistory`, cero
  upserts a `Trip`, y el registro queda `is_processed = 1`.
- **Efecto secundario:** `SdkSourceEvent.source_time` cae al fallback `datetime.now()` y
  `source_event_ref` cae al `id` de `SentianceEventos` (el `event.id` real nunca se extrae).
- **Documentación:** `MapeoSDK_BD.md` §9 documenta el tipo `TimelineEvents` como "array de
  `Event`" y nunca documenta el tipo `TimelineUpdate` con wrapper `{source, event}`.
  `Entregable.md` §3.1.1 (nota de equivalencias) tampoco lo registra — su censo de tipos
  (2026-04-04) es anterior a la aparición de `TimelineUpdate` en el stream.
- **Recomendación:** en `process_timeline_events()` agregar la rama
  `if "event" in payload: events = [payload["event"]]`, extraer `event.id`/`event.startTime`
  para `SdkSourceEvent`, documentar el wrapper en `MapeoSDK_BD.md` §9, y backfillear los
  `TimelineUpdate` ya marcados como procesados (reset de `is_processed` filtrado por tipo).

### C2. Los eventos `SDKStatus` se persisten con todas las columnas de estado NULL o 0

- **Payload real** (565 de 565 registros `SDKStatus` en el export de producción): el objeto
  de estado viene **anidado bajo la clave `sdkStatus`**, envuelto en metadata de dispositivo:
  ```json
  { "apiLevel": ..., "appVersion": ..., "brand": ..., "sentianceUserId": ...,
    "sdkStatus": { "startStatus": ..., "detectionStatus": ..., "canDetect": ..., ... } }
  ```
- **Código:** `process_sdk_status()` (`etl/sentiance_etl.py:832-863`) lee los campos en la
  **raíz** del payload → `start_status`, `detection_status`, `location_permission`,
  `quota_status_*` quedan NULL, y los booleanos (`precise_location_granted`,
  `is_location_available`, `can_detect`) quedan **0** (no NULL) por el patrón
  `1 if payload.get(...) else 0`. Es decir: corrupción silenciosa — la tabla parece poblada
  pero los flags son falsos negativos.
- **Bug adicional dentro del mismo handler:** lee `isPreciseLocationPermGranted`, pero tanto
  el SDK React Native (`scraped_site/wiki/api-reference/react-native/core/definitions.md`)
  como los payloads reales usan **`isPreciseLocationAuthorizationGranted`**.
- **Origen del error:** `Entregable.md` §4.7.4 y `MapeoSDK_BD.md` §10 documentan una interfaz
  `SdkStatus` desactualizada (sin wrapper, con `isPreciseLocationPermGranted`, y con un enum
  `DetectionStatus` que no coincide con el actual `DISABLED | EXPIRED | ENABLED_BUT_BLOCKED |
  ENABLED_AND_DETECTING`). El código siguió fielmente a esos documentos.
- **Recomendación:** en el handler, hacer `status = payload.get("sdkStatus", payload)` y
  corregir el nombre del campo de precisión; actualizar `Entregable.md` §4.7.4 y
  `MapeoSDK_BD.md` §10 con la definición actual del wiki; backfillear los 565+ registros.

---

## 2. Hallazgos ALTOS

### H1. `DrivingInsightsCallEvent.min/max_traveled_speed_mps` siempre NULL

- **SDK y payloads reales:** `minTraveledSpeedInMps` / `maxTraveledSpeedInMps`
  (definitions de driving-insights; confirmado en `test_small_full.json`, 4+4 ocurrencias).
- **Código:** `process_driving_insights_call_events()` (`etl/sentiance_etl.py:503-504`) lee
  `minTraveledSpeedMps` / `maxTraveledSpeedMps` (sin el `In`) → siempre `None`.
- **Triángulo de inconsistencia:** `MapeoSDK_BD.md` §4.1 tiene el campo SDK **correcto**
  (`minTraveledSpeedInMps`) pero la columna **incorrecta** (`min_travelled_speed_mps`, doble
  "l"; la real es `min_traveled_speed_mps`). El código tiene la columna correcta y el campo
  incorrecto.
- **Efecto cascada:** el bridge Movilidad lee esas columnas para armar `Eventos.llamados`
  (`etl/movilidad_bridge.py:525-529`) → los JSON de llamadas en Movilidad llevan
  velocidades `null`.
- **Recomendación:** corregir los dos `e.get(...)` en el ETL, corregir el nombre de columna
  en `MapeoSDK_BD.md` §4.1, y backfillear los CallEvents desde `SentianceEventos`.

### H2. El esquema de producción (RDS) NO es el esquema documentado

Verificado vía MCP `mssql` (host RDS, BD `VictaTMTK`):

- **Tablas existentes en producción:** `ArchivosOffload`, `ChoqueDeVehiculo`, `Conduccion`,
  `Eventos`, `EventosSignificantes`, `ManejoAnalisis_xx`, `MovDebug_Eventos`,
  `PerfilDeUsuario`, `PuntajesPrirmariosTr`, `PuntajesSecundariosTr`, `Recorridos`,
  `SentianceEventos`, `SentianceEventos_Errors`, `Transporte`.
  **No existen** `Trip`, `SdkSourceEvent`, `DrivingInsights*`, `UserContext*`,
  `TimelineEventHistory`, `SdkStatusHistory`, `VehicleCrashEvent`, `UserOrganization`, etc.
- **`SentianceEventos` en producción:** `id INT`, `sentianceid`, `fechahora DATETIME`,
  `json VARCHAR`, `tipo`, `created_at DATETIME`, `procesado BIT`, `app_version`.
  **No tiene `is_processed`** → la query central del ETL (`WHERE is_processed = 0`,
  `etl/sentiance_etl.py:984`) **falla contra producción** tal como está.
- **Documentos contradichos:**
  - `CLAUDE.md`: "Both `mssql` and `mssql-local` share this schema" — falso hoy.
  - `README.md`: "Use this in production or for bulk historical loads" — no ejecutable contra
    el RDS actual.
  - `DiccionarioDatos.md` §1 y `Entregable.md` §3.1.1 describen `SentianceEventos` con
    `is_processed`, `BIGINT`, `NVARCHAR(MAX)`, `DATETIME2(3)` y sin `fechahora`.
- **Interpretación probable:** el modelo relacional VictaTMTK (Stage 2) aún no fue desplegado
  en RDS; producción sigue con el layout legacy (landing zone + tablas estilo Movilidad).
- **Recomendación:** decidir y documentar el estado real del despliegue. Si el Stage 2 está
  pendiente: marcarlo explícitamente en README/CLAUDE.md ("solo local por ahora") y agregar
  el `ALTER TABLE SentianceEventos ADD is_processed BIT DEFAULT 0` al plan de despliegue.
  Si el despliegue va a otra base/esquema, actualizar la configuración MCP y los documentos.

### H3. Escala de `confidence`: tres documentos, tres versiones, y el código una cuarta

Fuente de verdad (documentación oficial en `scraped_site/wiki/`):
- Harsh events: `int`, **0–100** (`api-reference/android/driving-insights/harshdrivingevent.md`).
- Crash: **0–100**, "se recomienda filtrar < 50" (`important-topics/vehicle-crash-detection.md`).
- Payloads reales: enteros 38–59 ✔ confirma 0–100.

Inconsistencias:
| Fuente | Afirmación | ¿Correcta? |
|--------|-----------|------------|
| Código (`sentiance_etl.py:423,825`) | almacena el valor crudo (0–100) | ✔ funcional, pero ver overflow |
| `DiccionarioDatos.md` §7 | "el SDK devuelve int (0–100); **se almacena dividido por 100**" | ✘ el código NO divide |
| `DiccionarioDatos.md` §22 (crash) | "confianza (0 a 1)" | ✘ es 0–100 |
| `MapeoSDK_BD.md` §2.1 | "Confianza [0,1]" | ✘ es 0–100 |
| `MapeoSDK_BD.md` §11.1 | "Confianza [0,1]" | ✘ es 0–100 |

- **Riesgo de overflow:** las columnas son `NUMERIC(5,3)` (máximo 99.999). Un `confidence`
  de exactamente **100** produce arithmetic overflow → el registro entero cae a
  `SentianceEventos_Errors`.
- **Recomendación:** elegir UNA semántica. Opción simple: documentar 0–100 y ampliar a
  `NUMERIC(6,3)` o `TINYINT`. Opción alternativa: implementar la división por 100 que el
  diccionario ya promete (requiere migrar los datos existentes). Alinear los 3 documentos.

### H4. `analisis_mapeo_movilidad.md` §10 contradice el bridge actual

| Afirmación del documento | Realidad (código actual) |
|--------------------------|--------------------------|
| "proyecta hacia las **7 tablas** heredadas" | Son **9** (incluye `Conduccion`, `PerfilDeUsuario`, `ChoqueDeVehiculo`) |
| "`Conduccion` — Fuera de scope — **la tabla no existe** en el esquema Movilidad real" | Existe en producción y el bridge la puebla desde `eb5a361` (`movilidad_bridge.py:604-615`) |
| "`anticipacion` → **NULL**" | El bridge escribe **0** y la columna es `NOT NULL DEFAULT 0` (`init_movilidad.sql:81`) |
| Pasos de remoción: "revertir ... `self._movilidad_bridge`" y "`rm movilidad_bridge.py`" | No existe atributo `_movilidad_bridge` (el bridge se instancia local en `run()`); la ruta es `etl/movilidad_bridge.py` |

- **Recomendación:** actualizar §10 (tabla de decisiones y pasos de remoción) para reflejar
  las 9 tablas y el código real. El README ya está correcto; este documento quedó atrás.

---

## 3. Hallazgos MEDIOS

### M1. La variante "lista" de `TimelineEvents` rompe `run()` antes de llegar al handler

`process_timeline_events()` documenta soporte para payload tipo lista
(`etl/sentiance_etl.py:704-707`), pero en `run()` la extracción de `st` hace
`p.get("transportEvent", {})` **antes** de evaluar la rama `isinstance(p, list)`
(`etl/sentiance_etl.py:1038-1044`) → para una lista, `AttributeError` inmediato → el registro
se marca `-1` y va a la tabla de errores. La rama lista del handler es código muerto.
**Recomendación:** proteger la extracción (`p.get(...) if isinstance(p, dict) else ...`) o
eliminar la afirmación del docstring y de `MapeoSDK_BD.md` §9 ("El payload es un array").

### M2. `process_activity_history()` no puede matchear los valores del SDK

El SDK Core define `UserActivity.type` = `USER_ACTIVITY_TYPE_TRIP | ..._STATIONARY | ...`,
con `tripInfo.type` y `stationaryInfo.location`
(`scraped_site/wiki/api-reference/react-native/core/definitions.md`). El código lee
`activityType`, `tripType`, `stationaryLocation` y compara contra `"IN_TRANSPORT"`
(`etl/sentiance_etl.py:886-904`) — vocabulario que no existe en el SDK. `DiccionarioDatos.md`
§20 usa un tercer vocabulario (`TRIP`, `STATIONARY`). No se observan eventos `UserActivity`
en los datasets (el propio diccionario la marca legacy), pero si algún día llegan, no se
procesarán correctamente. **Recomendación:** documentar el renombre que haría la app, o
alinear el handler al SDK, o marcar el tipo como no soportado.

### M3. `CLAUDE.md` — lista de tablas incompleta y rutas imprecisas

1. La tabla "VictaTMTK Schema — Key Tables" omite 4 de las 24 tablas:
   `VehicleCrashEvent`, `SdkStatusHistory`, `TechnicalEventHistory`, `UserOrganization`.
2. La sección "Knowledge Base" dice que la documentación está en `wiki/` y que no se debe
   leer `raw/` — ambos viven bajo **`scraped_site/`** (`scraped_site/wiki/`,
   `scraped_site/raw/`); no existe `wiki/` en la raíz del repo.
3. El encabezado de la sección bridge dice "`movilidad_bridge.py`" (raíz); la ruta real es
   `etl/movilidad_bridge.py` (sí mencionada más abajo).
4. "Both `mssql` and `mssql-local` share this schema" — ver H2.

### M4. Conteos de tests desactualizados en dos documentos

- Real: **122 passed**.
- `README.md:51`: "114 tests".
- `tests/README.md`: "**94 unit tests**" en el encabezado; además el árbol de archivos omite
  `test_movilidad_bridge.py` y `test_user_organization.py`, y la sección "Handlers covered"
  no incluye los handlers nuevos.
- **Recomendación:** o se actualizan ambos, o mejor: reemplazar el número exacto por algo
  estable ("100+ tests") para que no envejezca con cada PR.

### M5. Enums y descripciones erróneas en `DiccionarioDatos.md` (vs. SDK oficial)

| Sección | Dice | SDK oficial dice |
|---------|------|------------------|
| §5 `transport_mode` | `CAR, WALK, RUN, BICYCLE, TRAIN` | `WALKING`, `RUNNING` (no `WALK`/`RUN`) |
| §8 `call_state` | `IN_HAND`, `MOUNTED` | `NO_CALL`, `CALL_IN_PROGRESS`, `UNAVAILABLE` |
| §16 `category` | `MOBILITY`, `LIFESTYLE` | `LEISURE`, `MOBILITY`, `WORK_LIFE` |
| §16 `subcategory` | `COMMUTER`, `SHOPPER` | `COMMUTE`, `SHOPPING`, ... |
| §16 `segment_type` | `CAR_DRIVER`, `TOWN_BOUND` | `CITY_DRIVER`, `TOWN_HOME`, `HOME_BOUND`, ... |
| §19 `event_type` | `OFFTHEGRID`, `INTRANSPORT` | `OFF_THE_GRID`, `IN_TRANSPORT` (con guiones bajos; también en `Detalle.md`) |
| §22 `severity` | `MINOR`, `MODERATE`, `SEVERE` | `UNAVAILABLE`, `LOW`, `MEDIUM`, `HIGH` |
| §22 `detector_mode` | `HIGH_G_ACCELEROMETER`, `IMPACT_FUSION` | `UNKNOWN`, `TWO_WHEELER`, `CAR` |
| §23 `detection_status` | `DETECTING`, `NOT_DETECTING`, `DISABLED`, `EXPIRED_DETECTION` | `DISABLED`, `EXPIRED`, `ENABLED_BUT_BLOCKED`, `ENABLED_AND_DETECTING` |
| §23 `location_permission` | `ALWAYS`, `WHILE_IN_USE` | `ALWAYS`, `ONLY_WHILE_IN_USE`, `NEVER` |
| §3 `payload_hash` | "MD5/SHA" | El código usa solo SHA-256 (y `Entregable.md` §3.9.1 ya decidió SHA-256) |
| §3 `source_event_ref` | "En TimelineEvents/UserContextUpdate almacena el event_id del SDK; en VehicleCrash el ID del choque" | `UserContextUpdate` y `VehicleCrash` no tienen `id` raíz → el código cae al fallback `SentianceEventos.id`. Solo el payload-lista de Timeline extraería `p[0].id` (rama hoy rota, ver M1) |
| §4 `UserMetadata` | "Actualmente no se usa" | Contradice §24 del mismo documento: el ETL intercepta `label='organizacion'` y puebla `UserOrganization` |

### M6. Errores puntuales en `MapeoSDK_BD.md`

1. Columnas FK de tablas hijas nombradas `source_event_id` (§§2,3,4,5,6,9,11) — la columna
   real es `sdk_source_event_id`.
2. §2.1 `magnitude` = "Fuerza G máxima" — para harsh events el SDK oficial dice **m/s²**
   (`harshdrivingevent.md`); en Gs está solo el crash (§11 sí es correcto;
   `DiccionarioDatos.md` §7 también es correcto con m/s²).
3. §4.1 columnas `min/max_travelled_speed_mps` (doble "l") — ver H1.
4. §10 `SdkStatus` desactualizado (campos y sin wrapper) — ver C2.
5. §11.1 `detectorMode` = `"CAR", "DRIVE"` — el enum es `UNKNOWN | TWO_WHEELER | CAR`.
6. §11.1 `precedingLocations` modelado como `{lat, lon, accuracy}` — el SDK define `Location`
   con `timestamp`, `altitude`, `provider` además.
7. §1 (intro) dice que los sub-eventos vienen "agregadas al payload por la App" dentro de
   `DrivingInsights` — contradice el propio §2 ("Tipo en producción:
   `DrivingInsightsHarshEvents`"), el docstring del ETL y los payloads reales (llegan como
   registros separados con `transportId`).
8. §9 documenta solo el tipo `TimelineEvents` como array — falta el tipo real `TimelineUpdate`
   con wrapper `{source, event}` (ver C1).

### M7. `Entregable.md`: recomendaciones de diseño nunca aterrizadas en el DDL

Las secciones §3.7 (índices recomendados), §3.8.1 (políticas FK), §3.8.2 (CHECK constraints,
incluido `chk_criteria_code` con `MANUAL_REQUEST`, marcado "Decisión arquitectónica: Opción A")
no existen en `development/sql/init_db.sql` (que solo tiene el índice de `UserOrganization` y
dos FKs en `Trip`). No es necesariamente un error — pero ningún documento aclara si están
pendientes, descartadas o aplicadas solo en producción (que hoy ni siquiera tiene esas tablas,
ver H2). **Recomendación:** una nota de estado en Entregable §3.7/§3.8 ("pendiente de
implementación en DDL") o incorporarlas a `init_db.sql`.

### M8. `development/README.md` desactualizado

- "Use the `fetch_sample_data.py` **(to be created)**" — ya existe.
- "Run `python sentiance_etl.py`" — la ruta actual es `etl/sentiance_etl.py` (el comando tal
  como está escrito falla desde cualquier directorio).
- No menciona `hydrate_local_small.py`/`hydrate_local_db.py` como vía principal de schema
  (sigue recomendando `bootstrap_local_db.py`), ni `reset_minimal_db.py`,
  `run_inspector_batch.py`, `driving_insights_graph.py`, `visualizador_arboles.py`.

---

## 4. Hallazgos BAJOS

1. **README diagrama de arquitectura** omite tres rutas del ETL: `UserMetadata` →
   `UserMetadata`/`UserOrganization`, `TechnicalEvent` → `TechnicalEventHistory`,
   `UserActivity` → `UserActivityHistory`. Además `README.md:401` dice "all **23** tables";
   el diccionario documenta **24**.
2. **`run_full_pipeline.py:69`**: el reporte de progreso cuenta `is_processed = 0` sin filtrar
   por los tipos que el ETL procesa → con tipos ignorados en cola (p. ej. `DebugLog`,
   descartado por diseño según Entregable §3.1.1 nota 3) el "remaining" nunca llega a 0.
   Cosmético (el loop termina igual por el retorno de `run()`).
3. **`movilidad_bridge._read_trip()`** (`etl/movilidad_bridge.py:183-221`): no filtra por
   `sentiance_user_id` y el `LEFT JOIN` a `DrivingInsightsTrip` puede devolver varias filas si
   un `DrivingInsights` se procesó dos veces (el handler hace `INSERT`, no `MERGE`) —
   `fetchone()` elige una arbitraria. Riesgo bajo con datos sanos; documentarlo o agregar
   `TOP 1 ... ORDER BY` determinístico.
4. **Logging:** `etl/sentiance_etl.py:68` configura `level=logging.DEBUG` global — muy verboso
   para producción; el header del archivo lo describe como "production-grade operational
   monitoring".
5. **Excepciones silenciadas:** `log_error_to_db` usa `except: pass` desnudo
   (`etl/sentiance_etl.py:229-230`); estilo a mejorar (registrar al menos en log local).
6. **`Mapeo de campos Sentiance CSV a React Native SDK.md`** referencia
   `DrivingInsightsTrip.transport_event_id`; la columna real es
   `canonical_transport_event_id`.
7. **`Detalle.md`** repite `OFFTHEGRID`/`INTRANSPORT` sin guiones bajos (ver M5) y
   `UserActivityHistory` con valores `TRIP/STATIONARY` (ver M2).

---

## 5. Verificado y CONSISTENTE ✔

Para balance, lo que se contrastó y está correcto:

- **SafetyScores:** los 10 campos (`smoothScore` … `attentionScore`) coinciden exactamente
  entre SDK, código, `init_db.sql`, `DiccionarioDatos.md` y `MapeoSDK_BD.md`, incluida la
  semántica [0,1].
- **TransportEvent → Trip/DrivingInsightsTrip:** nombres de campos, MERGE por
  `(canonical_transport_event_id, sentiance_user_id)`, descarte de provisionales,
  trazabilidad `creating/last_updated_by_sdk_source_event_id` — todo coincide con SDK y docs
  (incl. `development/README.md` § Schema Changes).
- **UserContext (`UserContextUpdate` y `requestUserContext`):** las dos formas de payload
  coinciden con el SDK; `criteria` enum correcto; `MANUAL_REQUEST` sintético implementado tal
  como decide Entregable ("Opción A", salvo el CHECK constraint — ver M7); `home`/`work` como
  `Venue{location,type}` bien leídos.
- **Harsh/Phone/Speeding/WrongWay events:** nombres de campos (`type`, `magnitude`,
  `callState`, `waypoints`, tiempos) correctos contra el SDK; el guard de huérfanos
  (skip + retry) coincide con docstrings, README y tests.
- **VehicleCrash:** todos los nombres de campos correctos (`time`, `location.*`, `magnitude`,
  `speedAtImpact`, `deltaV`, `confidence`, `severity`, `detectorMode`, `precedingLocations`).
- **Bridge Movilidad:** las 9 tablas y sus columnas coinciden con `init_movilidad.sql`
  (incluida la trampa `exceso_velocidad` sin `_de_` en `EventosSignificantes`, manejada y
  comentada); `Conduccion` poblada con `occupant_role`; README § bridge actualizado y preciso
  (tablas, condiciones de disparo, diagnóstico "Movilidad vacía", backfill).
- **`requirements.txt`** incluye `polyline` (dependencia del bridge) ✔.
- **`init_db.sql` ↔ `DiccionarioDatos.md`:** las 24 tablas y sus columnas/tipos coinciden
  (spot-check completo de tablas principales).
- **Suite de tests:** 122/122 verdes, sin BD, en ~0,3 s.

---

## 6. Pendientes de verificación externa

- **Movilidad producción (`AROCLNDSQL-DEV.ikeasistencia.com.ar:1533`):** inalcanzable desde
  esta red (`getaddrinfo ENOTFOUND` — probablemente requiere VPN). No se pudo confirmar que
  `init_movilidad.sql` siga espejando el esquema real (la fuente declarada es
  `Documentos/schemas.json`).
- El propósito/estado de las tablas de producción `ArchivosOffload`, `ManejoAnalisis_xx` y
  `MovDebug_Eventos` no está documentado en ningún archivo del repo.

---

## 7. Orden de remediación sugerido

1. **C2** — fix de `process_sdk_status` (wrapper + `isPreciseLocationAuthorizationGranted`) + backfill.
2. **C1** — fix de `process_timeline_events` (wrapper `{source, event}`) + backfill.
3. **H1** — fix de los nombres `min/maxTraveledSpeedInMps` + backfill de CallEvents.
4. **H3** — decidir semántica de `confidence` (sugerido: documentar 0–100 y ampliar columna).
5. **H2** — definir y documentar el plan de despliegue del Stage 2 en RDS (incl. `is_processed`).
6. **H4 + M3–M8** — pasada de actualización documental (un solo PR de docs).
7. **M1/M2** — limpiar las ramas muertas o documentarlas como no soportadas.

> Cada fix de código de los puntos 1–4 debería entrar con su test unitario que fije la forma
> real del payload (los payloads de `sample_payloads.json.gz` sirven como fixtures).

---

## Addendum (2026-06-11, misma sesión) — fixes aplicados + análisis de recencia de formatos

> **Contexto confirmado con el usuario:** el proyecto es nuevo y **nunca estuvo en
> producción**, así que **no hay migración ni backfill de datos** que hacer. El esquema
> canónico es `development/sql/init_db.sql` + Docker local como fuente de verdad; el RDS
> "producción" sólo tiene la landing zone legacy (ver H2). En prod, **el ETL debe procesar
> todas las filas pendientes** — no se aplica ningún filtro de recencia al pipeline. La
> recencia aplica únicamente a **qué filas mirar para verificar formato**.

### Fixes aplicados y verificados (125 tests verdes + verificación end-to-end en local)

| Hallazgo | Estado | Cambio |
|----------|--------|--------|
| **C2** SDKStatus | ✅ Corregido | `process_sdk_status` ahora desempaqueta `payload["sdkStatus"]` (con fallback a raíz) y lee `isPreciseLocationAuthorizationGranted`. Verificado contra fila real de prod. |
| **C1** TimelineUpdate | ✅ Corregido | `process_timeline_events` maneja el wrapper `{"source","event":{...}}`; además `run()` extrae `id`/`startTime` del objeto correcto según forma (arregla también **M1**, el crash latente con payloads lista). |
| **H1** CallEvent velocidades | ✅ Corregido | `min/maxTraveledSpeedInMps` (faltaba el `In`). |
| **H3** confidence overflow | ✅ Corregido | Se mantiene 0–100 (decisión del usuario); columnas `confidence` ampliadas `NUMERIC(5,3)`→`NUMERIC(6,3)` en `init_db.sql`; docs de §7/§22 (DiccionarioDatos) y §2.1/§11.1 (MapeoSDK) alineadas a 0–100. Verificado que `confidence=100` ya no va a `_Errors`. |

Tests nuevos en `tests/unit/` fijan las tres formas de payload reales (muestras de prod).
Verificación end-to-end: inyectando filas con la forma real en local, las tablas
`SdkStatusHistory`, `TimelineEventHistory` y las velocidades de `DrivingInsightsCallEvent`
se poblaron correctamente y `SentianceEventos_Errors` quedó en 0.

### Análisis de recencia de `tipo` (verificar formato sólo con filas nuevas)

Distribución de `tipo` por última aparición en `mssql` (prod), corte = últimos 3 meses
(desde ~2026-03-11; fecha de consulta 2026-06-11):

| `tipo` | Total | Últimos 3 meses | Última vez | Lectura |
|--------|------:|----------------:|-----------|---------|
| `requestUserContext` | 18.767 | 12.413 | 2026-06-11 | **activo** ✔ procesado |
| `DrivingInsights` | 32.088 | 13.667 | 2026-06-11 | **activo** ✔ |
| `userContextUpdate` | 6.710 | 3.258 | 2026-06-11 | **activo** ✔ (minúscula; matchea por collation CI) |
| `TimelineUpdate` | 5.308 | **5.308** | 2026-06-11 | **activo, 100% reciente** → motivo del fix **C1** |
| `SDKStatus` | 3.417 | 2.720 | 2026-06-11 | **activo** → motivo del fix **C2** |
| `DrivingInsightsPhoneEvents` | 47 | 23 | 2026-06-11 | activo ✔ |
| `getDrivingInsights` | 4 | 4 | 2026-06-06 | **reciente pero NO matchea** el ETL (≠ `DrivingInsights`). Sólo 4 filas; probable llamada manual/debug. |
| `DrivingInsightsHarshEvents` | 28 | 15 | 2026-06-06 | activo ✔ |
| `DrivingInsightsSpeedingEvents` | 16 | 9 | 2026-06-05 | activo ✔ |
| `VehicleCrash` | 564 | 94 | 2026-06-02 | activo ✔ |
| `DebugLog` | 150 | 77 | 2026-03-16 | ignorado por diseño (Entregable §3.1.1) |
| `DrivingInsightsCallEvents` | 2 | 0 | 2026-03-03 | raro (sólo 2 históricos); fix **H1** correcto igual |
| `TimelineEvents` | 35 | 0 | 2026-02-25 | **legacy** (reemplazado por `TimelineUpdate`) |
| `SdkStatusUpdate` | 8 | 0 | 2025-12-16 | **legacy/muerto** — no es preocupación de formato vigente |
| `UserActivityUpdate` | 112 | 0 | 2025-10-08 | **legacy/muerto** |
| `CRASH` | 63 | 0 | 2025-10-06 | **legacy/muerto** — contiene payloads UserActivity mal etiquetados; sólo dato histórico |
| `fcm_token` / `offload` / `context` | 21 | 0 | ≤2025-12 | **legacy/muerto** |

**Conclusión:** los `tipo` "raros" que se habían marcado como dudas de scope
(`CRASH`, `UserActivityUpdate`, `SdkStatusUpdate`) son **datos legacy** (nada en los últimos
3 meses) y **no representan el formato vigente**. Verificando formato sólo con filas nuevas,
los formatos activos de alto volumen son `DrivingInsights`, `requestUserContext`,
`userContextUpdate`, `TimelineUpdate` y `SDKStatus` — todos manejados (los fixes C1/C2 apuntan
precisamente a los dos formatos activos que estaban rotos). Único pendiente menor en datos
recientes: `getDrivingInsights` (4 filas, no matchea el ETL) — evaluar si descartar o mapear.
