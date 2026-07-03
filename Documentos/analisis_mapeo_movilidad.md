# Análisis de Mapeo: Movilidad (CSVs/Offloads) vs. SentianceEventos (SDK/REST)

Este documento detalla el análisis y equivalencia entre la información alojada actualmente en las tablas de Movilidad (alimentadas por archivos CSV provenientes de los *Offloads* de la nube de Sentiance) y la recopilación de datos directa desde la tabla origen `SentianceEventos` (obtenida on-device a través del SDK de Sentiance y enviada vía REST por la aplicación móvil).

> **Objetivo:** Confirmar que todos los campos y métricas derivadas de los *Offloads* pueden obtenerse, calcularse o subsanarse a partir del payload crudo arrojado por el dispositivo localmente (`DrivingInsight`, `UserContext`, y `TransportEvent`).

---

## 1. Tabla `Transporte`
**Origen CSV:** `transports.csv`
**Campos:** `modo_transporte`, `comienzo`, `fin`, `duracion`, `metadata`, `velocidad_maxima`

**Equivalencia en el SDK (`TransportEvent` / `DrivingInsight`):**
*   **`modo_transporte`:** El SDK entrega `transportMode` en inglés (`CAR`, `BUS`, `WALKING`, …); el bridge lo **traduce al vocabulario español** que usa Movilidad: `CAR→Auto`, `BUS→Colectivo`, `MOTORCYCLE→Moto`, `WALKING→Caminando`, `BICYCLE→Bicicleta`, `TRAIN→Tren`, `TRAM→Subte`, `UNKNOWN→Desconocido` (`IDLE`/`RUNNING` se conservan en inglés, igual que Movilidad). Validado contra el Movilidad real (2026-07-03): 100% de coincidencia sobre la intersección.
*   **`comienzo`, `fin`:** Mapeado a `startTimeEpoch` / `endTimeEpoch` (y `startTime` / `endTime` ISO strings).
*   **`duracion`:** Mapeado a `durationInSeconds`.
*   **`velocidad_maxima`:** El SDK no expone globalmente este valor a nivel `TransportEvent`. **Movilidad tampoco lo computa en `Transporte`: guarda `-1` en el 100% de sus filas**, así que el bridge escribe `-1` acá. La velocidad máxima real (derivada del máximo de `speedInMps` en `waypoints`, en km/h) va en `Recorridos.maxima_velocidad`.
*   **`metadata`:** El objeto `transportTags` incluye la metadata asociada configurada en el viaje.

✅ **Conclusión:** Plenamente representable partiendo de la estructura del SDK.

---

## 2. Tabla `Recorridos`
**Origen CSV:** `trajectories.csv`
**Campos:** `distancia_m`, `polyline`, `puntos_recorrido`, `ubicacion_inicio`, `ubicacion_fin`, `maxima_velocidad`

**Equivalencia en el SDK (`TransportEvent`):**
*   **`distancia_m`:** `distance` **× 100** — Movilidad guarda la distancia en **centímetros** (entero), no en metros.
*   **`maxima_velocidad`:** máximo de `speedInMps` en `waypoints` **× 3.6** (km/h entero). Movilidad usa su propio algoritmo, así que el valor exacto difiere; reproducimos formato y orden de magnitud.
*   **`puntos_recorrido`:** cada waypoint reformateado al esquema de Movilidad: `{latitude, longitude, timestamp (ISO en hora local del viaje), road_type:"unknown", speed (m/s), speed_limit (m/s), distance:-1.0, speed_v2_confidence:0.0}`.
*   **`polyline`:** El payload del SDK **no devuelve un string Polyline codificado**; se genera on-backend con la librería `polyline` (PyPI) a partir de los `waypoints`.
*   **`ubicacion_inicio` / `ubicacion_fin`:** **Movilidad nunca resuelve geocoding reverso**: guarda el objeto constante `{"country":"unknown","region":"unknown","city":"unknown","district":"unknown","street":"unknown"}` en el 100% de sus filas. El bridge escribe ese mismo objeto (no coordenadas ni geocoding).

✅ **Conclusión:** Reproducible partiendo de `waypoints`. Se prioriza formato + orden de magnitud (no el valor exacto de los algoritmos internos de Movilidad).

> **Nota sobre la hora local:** los timestamps de `puntos_recorrido` (y de `Eventos`, sección 6) usan la hora local del viaje. El offset se deriva por viaje comparando `Trip.start_time` (que ya viene en local) contra el UTC del primer waypoint, redondeado a 15 minutos — sin librería de timezones.

---

## 3. Tabla `Conduccion`
**Origen CSV:** No aplica explícitamente a un CSV independiente (o derivable de los transportes y user-context).
**Campos vitales:** `ocupante` (Driver, Passenger).

**Equivalencia en el SDK:**
*   **`ocupante`:** El SDK entrega `occupantRole` en inglés (`"DRIVER"`, `"PASSENGER"`, `"UNAVAILABLE"`); el bridge lo **traduce** a `Conductor`, `Pasajero`, `No disponible` (vocabulario de Movilidad). Validado contra el Movilidad real (2026-07-03): 100% de coincidencia.

✅ **Conclusión:** Mapeo directo, con traducción del vocabulario al español.

---

## 4. Tablas `PuntajesPrirmariosTr`
**Origen CSV:** `primary_safety_scores_transports.csv`
**Campos:** `legal`, `suavidad`, `atencion`, `promedio`

**Equivalencia en el SDK (`DrivingInsight.safetyScores`):**
*   **`legal`:** `legalScore`
*   **`suavidad`:** `smoothScore`
*   **`atencion`:** `focusScore` (⚠️ **no** `attentionScore`). Verificado contra el Movilidad real (2026-07-03): con `focusScore` la coincidencia es 99% vs 33% con `attentionScore`. Nota: tanto `atencion` (acá) como `concentracion` (Secundarios) salen del mismo `focusScore`.
*   **`promedio`:** `overallScore`
*   *Scores ausentes:* si el SDK no trae un score (`null`), se escribe `-1` ("sin dato"), no `0` — igual que el Movilidad real. Un `0.0` real se conserva.

✅ **Conclusión:** Completo soporte mediante la inferencia base del SDK, el objeto `SafetyScores` proporciona los niveles primarios crudos.

---

## 5. Tabla `PuntajesSecundariosTr`
**Origen CSV:** `secondary_safety_scores_transports.csv`
**Campos:** `concentracion`, `aceleracion_fuerte`, `frenado_fuerte`, `curvas_fuertes`, `anticipacion`, `celular_fijo`, `eventos_fuertes`

**Equivalencia en el SDK (`DrivingInsight.safetyScores` y conteos crudos):**
*   **`concentracion`:** `focusScore`
*   **`aceleracion_fuerte`:** `harshAccelerationScore`
*   **`frenado_fuerte`:** `harshBrakingScore`
*   **`curvas_fuertes`:** `harshTurningScore`
*   **`eventos_fuertes`:** Debe procesarse en Backend haciendo la cuenta total o suma de los arreglos locales de Harsh Events recibidos en cada viaje del SDK.
*   **`anticipacion`:** ❌ **No está disponible en el SDK**. Sentiance Cloud procesa el *Anticipative Score* agregando reglas complejas cruzadas entre giros y mapas, lo que no sucede de forma on-device. Su propiedad carece de un mapping dentro de los interfaces TS/Swift/Kotlin de la SDK local provista. Se escribe **`-1`** ("sin dato"), igual que el Movilidad real (que tiene `-1` en el 100% de sus filas).
*   **`celular_fijo` (score/count global):** ❌ Las detecciones globales de celular montadose realizan en la nube (`Mounted`). La alternativa es estimarlo mediante eventos específicos de telefonía y su `handsFreeState` devuelto. Se escribe **`-1`** ("sin dato"), igual que el Movilidad real.

⚠️ **Conclusión:** Limitación importante: El puntaje de anticipación no se replica si se corta el proceso Cloud. Los scores base de frenos y aceleración sí persisten.

---

## 6. Tablas `Eventos` y `EventosSignificantes`
**Origen CSV:** `driving_events_all.csv`, `driving_events_significant.csv`
**Campos a mapear en columnas Json/Text:** `aceleracion`, `uso_telefono`, `curvas`, `celular_fijo`, `frenado`, `exceso_de_velocidad`, `llamados`, `pantalla`

**Equivalencia bajo API On-Device SDK:**
El SDK expone eventos a través de arrays obtenidos asíncronamente luego del transporte:
*   **`aceleracion`:** Creado recorriendo objetos `HarshDrivingEvent` filtrados por donde la propiedad `.type === "ACCELERATION"`.
*   **`frenado`:** `HarshDrivingEvent` filtrados por `.type === "BRAKING"`.
*   **`curvas`:** `HarshDrivingEvent` filtrados por `.type === "TURN"`.
*   **`llamados`:** Emitido en nativo bajo la estructura objetual completa de `CallEvent`.
*   **`uso_telefono`:** Emitido bajo `PhoneUsageEvent` (`callState`).
*   **`exceso_de_velocidad`:** Emitido bajo `SpeedingEvent` / `WrongWayDrivingEvent`.
*   **`pantalla`:** ❌ **Aviso Crítico.** Sentiance realiza la categorización y separación de eventos base en "Screen Usage" y "Phone Handling" apoyado en modelos de ML en la nube. A nivel SDK on-device, este detalle *Screen Use* no viene especificado en sí. Deben apalancarse de `PhoneUsageEvent` como entidad unificadora, lo cual puede implicar pérdida de granularidad entre sólo prender la pantalla vs. teclear activamente.
*   **`celular_fijo`:** El único registro local donde Sentiance reporta *mounted* de forma similar es usando la propiedad `handsFreeState == "HANDS_FREE"` en `CallEvent`. No existe un sub-evento general y global de montar el celular a nivel de *Timeline SDK*.
*   **Eventos significantes:** hoy `EventosSignificantes` es un espejo idéntico de `Eventos` (sin umbral aún; ver Decisiones §7.3).

**Esquema de salida (formato exacto de Movilidad que reproduce el bridge):**
Cada columna es un array JSON. Los timestamps van en hora local del viaje (ver §2, nota de hora local).
*   **`aceleracion` / `frenado` / `curvas`** (de `HarshDrivingEvent`): `{duration, path:[{latitude,longitude}], magnitude, start_at, end_at, type, category}`. `type`/`category`: `accelerate`/`accelerating`, `brake`/`braking`, `turn`/`turning`. `aceleracion` y `frenado` incluyen además `mean` (= `magnitude`); `curvas` no.
*   **`uso_telefono`** (de `PhoneUsageEvent`): `{duration, path, start_at, end_at, type:"phone_handling", category:"phone_handling"}`.
*   **`llamados`** (de `CallEvent`): `{duration, start_at, end_at, type:"call_events", category:"call_events"}` (sin `path`).
*   **`exceso_de_velocidad`** (de `SpeedingEvent` + `WrongWayDrivingEvent`): `{duration, path, start_at, end_at, type:"speeding", category:"speeding", speed_limits:[km/h], speeds:[km/h]}` (derivados de `speedLimitInMps` / `speedInMps` de los waypoints).
*   **`celular_fijo` / `pantalla`:** `"[]"` (cloud-only, no disponible por SDK).

✅ **Conclusión:** El **formato** de todas las columnas de eventos es idéntico al de Movilidad (validado campo a campo). El **contenido** puede diferir porque el CSV histórico de Movilidad tiene eventos que la ventana del SDK no capturó, pero el esquema que consume el cliente es el mismo.

---

## 7. Tabla `PerfilDeUsuario`
**Campos:** `usuario`, `json`
**Equivalencia:** Toda esta información estará resguardada de forma natural al invocar la API de `UserContext` de Sentiance (`getUserContext`), recuperando un abanico inmenso de semánticas vinculadas al usuario como rutinas, segmentos, sub-segmentos (ej. `Home`, `Work`), que pueden simplemente volcarse bajo el campo crudo JSON de dicha tabla SQL.

### Decisiones de Negocio y Reglas para AWS Lambda

Con la retroalimentación del negocio, estas son las definiciones que conformarán las reglas de la función de Ingesta (AWL Lambda):

1.  **Omisión de Novedades No-Soportadas Nativamente:** 
    *   `anticipacion`, `celular_fijo` y `pantalla` **no bloquearán** el desarrollo porque se ignorarán completamente. Los scores numéricos (`anticipacion`, `celular_fijo` en Secundarios) se guardan como **`-1`** ("sin dato", igual que Movilidad); las columnas de listas JSON (`pantalla`, `celular_fijo` en Eventos) como `"[]"`. Así se cumple el schema sin detener la importación del viaje.
2.  **Tabla de Recorridos (`polyline`):**
    *   Actualmente la BD SQL requiere estrictamente la string de la columna (campo NOT NULL).
    *   Para satisfacer este esquema actual, la función Lambda construirá automáticamente el string cifrado *Polyline* a partir del listado serializado de `waypoints` crudos extraídos de la Payload (`TransportEvent.waypoints`). No interviene procesamiento extra-complejo, sino una simple librería de encoding (ej. la librería de Python `polyline` o `google-polyline` de NodeJS en Lambda).
3.  **Filtrado de `EventosSignificantes`:**
    *   Dado que no hay heurística para definir un nivel significativo hoy por hoy, todos los Eventos recolectados por Sentiance (aceleración, frenado, choques, uso de teléfono) poblarán de manera espejo **tanto la tabla `Eventos` como `EventosSignificantes`** temporalmente, o en su defecto, pospondremos el llenado de la tabla `Significantes` hasta que Operaciones defina los umbrales específicos de velocidad o gravedad `magnitude`.

---

## 8. Arquitectura de Ingesta: CSVs Históricos vs. Datos Crudos (REST)

Existe una diferencia fundamental entre los archivos CSV heredados y los datos que ahora ingresan a la tabla `SentianceEventos`:

1.  **Archivos CSV (`csv/`)**: Son "snapshots" o exportaciones procesadas que provenían del servicio Cloud de Sentiance (o de un pipeline de agregación anterior). Muestran los datos ya estructurados por la nube de Sentiance. Por eso algunos viajes antiguos tienen eventos allí, que tal vez nunca pasaron por el nuevo pipeline REST.
2.  **Tabla `SentianceEventos`**: Contiene la telemetría **cruda (raw) y más reciente** enviada directamente por la aplicación móvil vía REST. Por este motivo, viajes súper recientes (ej. `2925a3a1-18a2-4da6-94f2-3091a0f22709`) se encuentran aquí con todo su nivel de detalle, pero no constan en los CSVs viejos.

### Estructura de Eventos para la Función AWS Lambda

La app móvil no envía un único "mega JSON" con todo el viaje consolidado. En su lugar, envía **múltiples registros separados** que la función de AWS Lambda deberá interceptar, decodificar y agrupar utilizando la clave foránea `transportId`.

A continuación, ejemplos reales extraídos de la base de datos para el viaje `2925a3a1-18a2-4da6-94f2-3091a0f22709`:

#### A) Viaje Principal (`tipo = 'DrivingInsights'`)
Llega al finalizar el recorrido e incluye inicio, fin, ruta (`waypoints`) y puntajes generales (`safetyScores`).
*(La Lambda lo insertará primeramente en `Transporte`, `Recorridos`, etc. y creará la fila inicial en `Eventos`).*

#### B) Eventos Bruscos (`tipo = 'DrivingInsightsHarshEvents'`)
Contiene arreglos de frenadas (`BRAKING`), aceleraciones (`ACCELERATION`) y giros (`TURN`).
```json
{
  "transportId": "2925a3a1-18a2-4da6-94f2-3091a0f22709",
  "events": [
    {
      "type": "BRAKING",
      "magnitude": 4.042,
      "confidence": 57,
      "startTime": "2026-03-01T19:44:49.984-0300",
      "waypoints": [...]
    },
    {
      "type": "ACCELERATION",
      "magnitude": 2.563,
      "confidence": 59,
      "startTime": "2026-03-01T19:50:54.205-0300"
    }
  ]
}
```
*-> Lambda mapeará `BRAKING` a la columna `frenado` y `ACCELERATION` a la columna `aceleracion`.*

#### C) Excesos de Velocidad (`tipo = 'DrivingInsightsSpeedingEvents'`)
```json
{
  "transportId": "2925a3a1-18a2-4da6-94f2-3091a0f22709",
  "events": [
    {
      "startTime": "2026-03-01T19:43:27.362-0300",
      "endTime": "2026-03-01T19:43:32.362-0300",
      "waypoints": [...]
    }
  ]
}
```
*-> Lambda insertará estos tramos en la columna `exceso_de_velocidad`.*

#### D) Uso de Teléfono (`tipo = 'DrivingInsightsPhoneEvents'`)
Reporta la manipulación del teléfono.
```json
{
  "transportId": "2925a3a1-18a2-4da6-94f2-3091a0f22709",
  "events": [
    {
      "callState": "NO_CALL",
      "startTime": "2026-03-01T19:38:45.805-0300",
      "endTime": "2026-03-01T19:38:57.805-0300",
      "waypoints": [...]
    }
  ]
}
```
*-> Lambda mapeará este array a la columna `uso_telefono`.*

#### E) Otros eventos disponibles a correlacionar
*   `DrivingInsightsCallEvents` -> Para popular la columna `llamados`.
*   `VehicleCrash` -> Para identificar accidentes.

**Estrategia recomendada para la Lambda**: La función de SQS a Lambda deberá leer el `tipo` proveniente del JSON recibido vía REST, extraer el `transportId`, y ejecutar una sentencia `UPDATE Eventos SET {columna_relevante} = '{nuevo_json}' WHERE viaje = '{transportId}'` utilizando lógica de Upsert, ya que los mensajes pueden llegar de forma asíncrona o desordenada.

---

## 9. Limitación Confirmada: Retroactividad de Datos de Eventos Históricos

Durante el chequeo cruzado de viajes históricos obtenidos desde la nube de Sentiance (`driving_events_all.csv`) y los recabados localmente por la arquitectura actual dentro de la tabla cruda `SentianceEventos`, se descubrió una condición vital del esquema heredado:

*   **Pérdida de eventos crudos on-device para historial antiguo:** Viajes del pasado (por ejemplo, del 20 de marzo) **SÍ** constan en `SentianceEventos`, **PERO** constan únicamente bajo su registro principal de tipo `DrivingInsights`. Los mensajes separados y granulares de tipo `DrivingInsightsHarshEvents` o `DrivingInsightsPhoneEvents` **no fueron insertados en la base de datos SQL**.
*   **Motivo:** En ese período, la aplicación móvil no enviaba (o el servidor no persistía) los tópicos granulares extra, o bien provenían de un proceso que la Nube consumía y encapsulaba antes de la implementación actual del endpoint REST.
*   **Consecuencia de Negocio:** No se puede armar o retroalimentar la tabla `Eventos` de los viajes antiguos usando *únicamente* la SQL `SentianceEventos`, los JSON de las frenadas y teléfonos crudos de esa fecha **se perdieron en el esquema local**.
*   **Estado Actual:** Esta limitación sólo aplica hacia el pasado. En los registros **nuevos** (recabados recientemente), el sistema envía y almacena exitosamente toda la familia de eventos vinculables bajo el mismo ID de viaje (`transportId`). Por ende, la AWS Lambda se deberá codificar apuntando primordialmente al tráfico en vivo (On-going y futuro) que sí cumple con la entrega en forma distribuida.

---

## 10. Plan de implementación (Bridge ETL temporal)

> **Estado:** implementado en `movilidad_bridge.py`, gated por la variable `ENABLE_MOVILIDAD_BRIDGE=true`.

Mientras Operaciones implementa el proceso definitivo que va a leer VictaTMTK y poblar Movilidad por su cuenta, el ETL actual (`sentiance_etl.py`) cuenta con un **bridge temporal** que proyecta los datos de VictaTMTK hacia las 7 tablas heredadas de Movilidad al final de cada batch.

### Arquitectura

```
SentianceEventos (REST) ──► sentiance_etl.py ──► VictaTMTK (fuente de verdad)
                                  │
                                  └── bridge (al final del batch)
                                        │
                                        ▼
                                  Movilidad (proyección heredada)
```

### Decisiones de diseño aplicadas

| Tema | Decisión |
|------|----------|
| Aislamiento | Toda la lógica en `movilidad_bridge.py` + ~15 líneas en `sentiance_etl.py`. |
| Fuente | Lee de **VictaTMTK** (no del JSON crudo). El día que se borre el bridge, su reemplazo natural también lee de VictaTMTK. |
| Idempotencia | `MERGE` en SQL Server por clave `(viaje, usuario)` en cada upsert. |
| Tolerancia a fallos | Si Movilidad está caída, log warning y se continúa. No bloquea el ETL principal. |
| `polyline` | Codificado con la librería `polyline` de PyPI (`pip install polyline`). |
| `distancia_m` | Metros × 100 (Movilidad guarda **centímetros**, entero). |
| `maxima_velocidad` (Recorridos) | m/s × 3.6 (**km/h** entero). Formato+magnitud, no el valor exacto de su algoritmo. |
| `velocidad_maxima` (Transporte) | `-1` (Movilidad no lo computa a nivel Transporte). |
| `ubicacion_inicio` / `ubicacion_fin` | Objeto constante `{"country":"unknown",...}` — Movilidad **nunca** geocodifica. |
| `puntos_recorrido` / `Eventos` | Reformateados al esquema JSON exacto de Movilidad (§2 y §6); timestamps en hora local del viaje. |
| Criterio de paridad | **Formato (obligatorio) + orden de magnitud**, no el valor exacto — para no romper software del cliente que consume estas columnas. |
| `EventosSignificantes` | Espejo idéntico de `Eventos` hasta que Operaciones defina umbrales (sección 7.3). Atención: la columna se llama `exceso_velocidad` (sin `_de_`). |
| `anticipacion` | `-1` ("sin dato"; cloud-only ML, no expuesto por SDK). |
| `celular_fijo` (Secundarios, numérico) / `pantalla` (Eventos, lista) | `-1` / `"[]"` (cloud-only ML). |
| Scores ausentes (`legal`/`suavidad`/`atencion`/`promedio`) | `-1` si el SDK no los trae (no `0`); `0.0` real se conserva. |
| `modo_transporte` / `ocupante` | Traducidos al vocabulario español de Movilidad (validado 100%). |
| `atencion` | Sale de `focusScore`, **no** `attentionScore` (validado 99% vs 33%). |
| `Conduccion` | **Sí existe** en el Movilidad real; se puebla con `ocupante` traducido. |

### Variables de entorno

```
ENABLE_MOVILIDAD_BRIDGE=true        # "false" o ausente desactiva el bridge
MOVILIDAD_HOST=AROCLNDSQL-DEV.ikeasistencia.com.ar
MOVILIDAD_PORT=1533
MOVILIDAD_DATABASE=Movilidad
MOVILIDAD_USER=<usuario>
MOVILIDAD_PASSWORD=<password>
```

### Cómo remover el bridge cuando Operaciones tenga su proceso propio

1. `rm movilidad_bridge.py tests/unit/test_movilidad_bridge.py`
2. En `sentiance_etl.py`, revertir:
   - El bloque `try: from movilidad_bridge import MovilidadBridge ...` cerca de los imports.
   - Las líneas en `__init__` que setean `_movilidad_enabled`, `_movilidad_bridge` y `_dirty_transport_ids`.
   - El bloque en `run()` que captura `candidate_tid` en el dispatch.
   - El bloque final en `run()` que llama `self._movilidad_bridge.sync_trips(...)`.
3. Quitar la variable `ENABLE_MOVILIDAD_BRIDGE` y las `MOVILIDAD_*` del `.env`.

El resto del ETL queda exactamente igual.

### Limitaciones conocidas

- **PerfilDeUsuario** se sincroniza con el último `UserContextHeader` por usuario; no incluye los segmentos/atributos detallados (basta para el caso de uso actual de Movilidad, pero pierde granularidad respecto al payload original).
- **ChoqueDeVehiculo** no tiene clave natural en Movilidad: la deduplicación se hace por `(usuario, crash_time_epoch)` parseando el JSON. Es funcionalmente correcto pero no aprovecha índices.
- El bridge **no maneja eventos huérfanos** (child sin parent). Si un `DrivingInsightsHarshEvent` llega antes que su `DrivingInsights`, el bridge no encontrará el Trip y omitirá ese `transport_id`. En el siguiente batch que toque al Trip, se re-sincroniza completo.
