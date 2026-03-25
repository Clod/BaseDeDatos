# Análisis de Mapeo: Movilidad (CSVs/Offloads) vs. SentianceEventos (SDK/MQTT)

Este documento detalla el análisis y equivalencia entre la información alojada actualmente en las tablas de Movilidad (alimentadas por archivos CSV provenientes de los *Offloads* de la nube de Sentiance) y la recopilación de datos directa desde la tabla origen `SentianceEventos` (obtenida on-device a través del SDK de Sentiance y transmitida vía AWS IoT MQTT).

> **Objetivo:** Confirmar que todos los campos y métricas derivadas de los *Offloads* pueden obtenerse, calcularse o subsanarse a partir del payload crudo arrojado por el dispositivo localmente (`DrivingInsight`, `UserContext`, y `TransportEvent`).

---

## 1. Tabla `Transporte`
**Origen CSV:** `transports.csv`
**Campos:** `modo_transporte`, `comienzo`, `fin`, `duracion`, `metadata`, `velocidad_maxima`

**Equivalencia en el SDK (`TransportEvent` / `DrivingInsight`):**
*   **`modo_transporte`:** Mapeado directo a `transportMode` (ej. `CAR`, `BUS`).
*   **`comienzo`, `fin`:** Mapeado a `startTimeEpoch` / `endTimeEpoch` (y `startTime` / `endTime` ISO strings).
*   **`duracion`:** Mapeado a `durationInSeconds`.
*   **`velocidad_maxima`:** El SDK no expone globalmente este valor en el nivel primario de la clase `TransportEvent`, pero puede ser inferido fácilmente iterando sobre los elementos del vector `waypoints` y obteniendo el máximo de la propiedad `speedInMps`.
*   **`metadata`:** El objeto `transportTags` incluye la metadata asociada configurada en el viaje.

✅ **Conclusión:** Plenamente representable partiendo de la estructura del SDK.

---

## 2. Tabla `Recorridos`
**Origen CSV:** `trajectories.csv`
**Campos:** `distancia_m`, `polyline`, `puntos_recorrido`, `ubicacion_inicio`, `ubicacion_fin`, `maxima_velocidad`

**Equivalencia en el SDK (`TransportEvent`):**
*   **`distancia_m`:** Mapeado a `distance`.
*   **`puntos_recorrido`:** Mapeado directamente a la lista en `waypoints` (arrays de objetos con lat, lon, precisiòn, velocidad y límites).
*   **`polyline`:** El payload del SDK **no devuelve un string Polyline codificado**. Generar la Polyline se debe realizar on-backend utilizando los `waypoints` recolectados o librerías estándar en el Lambda (p. ej: polyline.js / python polyline decoder).
*   **`ubicacion_inicio` / `ubicacion_fin`:** Geocoding reverso textual (ej. texto de una calle o ciudad) no está resuelto nativamente a nivel `TransportEvent`. Se requieren las coordenadas del primer/ultimo waypoint o usar nodos semánticos (Locations) del payload `UserContext` para obtener su equivalencia.

⚠️ **Conclusión:** Información geoespacial está ahí (`waypoints`), pero métricas formales como textos geocodificados (Geo-decoding inverso) deberán procesarse en backend para suplir aquello que la nube Sentiance realizaba previamente.

---

## 3. Tabla `Conduccion`
**Origen CSV:** No aplica explícitamente a un CSV independiente (o derivable de los transportes y user-context).
**Campos vitales:** `ocupante` (Driver, Passenger).

**Equivalencia en el SDK:**
*   **`ocupante`:** Mapeado directamente al campo `occupantRole` provisto bajo `TransportEvent`. Los valores emitidos por SDK son explícitamente `"DRIVER"`, `"PASSENGER"` y `"UNAVAILABLE"`.

✅ **Conclusión:** Mapeo directo y transparente.

---

## 4. Tablas `PuntajesPrirmariosTr`
**Origen CSV:** `primary_safety_scores_transports.csv`
**Campos:** `legal`, `suavidad`, `atencion`, `promedio`

**Equivalencia en el SDK (`DrivingInsight.safetyScores`):**
*   **`legal`:** `legalScore`
*   **`suavidad`:** `smoothScore`
*   **`atencion`:** `attentionScore`
*   **`promedio`:** `overallScore`

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
*   **`anticipacion`:** ❌ **No está disponible en el SDK**. Sentiance Cloud procesa el *Anticipative Score* agregando reglas complejas cruzadas entre giros y mapas, lo que no sucede de forma on-device. Su propiedad carece de un mapping dentro de los interfaces TS/Swift/Kotlin de la SDK local provista.
*   **`celular_fijo` (score/count global):** ❌ Las detecciones globales de celular montadose realizan en la nube (`Mounted`). La alternativa es estimarlo mediante eventos específicos de telefonía y su `handsFreeState` devuelto.

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
*   **Eventos significantes:** Si desean separar "Todos" de "Significantes", se tendrán usar de las propiedades `magnitude` y `confidence` presentes en eventos como `HarshDrivingEvent` para segmentarlos lógicamente en la BD en base a umbrales propios.

⚠️ **Conclusión:** Gran parte está mapeable con reestructuración en el parsing Backend. Existen brechas conceptuales menores, originadas porque las versiones de eventos que la Nube Sentiance expone, atraviesan modelos de Machine Learning superiores que separan "pantalla", "manipulación" y "soporte" con más rigurosidad de lo que el chip móvil computa por su cuenta.

---

## 7. Tabla `PerfilDeUsuario`
**Campos:** `usuario`, `json`
**Equivalencia:** Toda esta información estará resguardada de forma natural al invocar la API de `UserContext` de Sentiance (`getUserContext`), recuperando un abanico inmenso de semánticas vinculadas al usuario como rutinas, segmentos, sub-segmentos (ej. `Home`, `Work`), que pueden simplemente volcarse bajo el campo crudo JSON de dicha tabla SQL.

## Resumen de hallazgos
La transición a *SentianceEventos* permite reconstruir más del 90-95% del ecosistema de las tablas analíticas, optimizándolo en tiempo real, pero el equipo de BackEnd deberá considerar las siguientes tareas en su Lambda de recolección:
1.  **Detecciones Complejas Ausentes:** Scores como el *"Anticipative driving"* y eventos granulados *"Screen events"* exclusivos o *"Mounted events"* exclusivos (fuera de llamadas) no son soportados localmente. Si son excluyentes para el negocio, se requiere lógica interna propia para re-derivar.
2.  **Transformaciones Geográficas:** Generar manualmente la string de `polyline` usando enrutadores y las coordenadas array provistas.`
3.  **Computación de eventos:** Contar y filtar los eventos "fuertes" en base a atributos como severidad/magnitud expuestos en el Payload base.
