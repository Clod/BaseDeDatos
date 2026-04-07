# **Documentación del Esquema de Base de Datos (Sentiance)**

## **Objetivo**

El objetivo de esta base de datos es procesar, estructurar y almacenar de manera persistente y consultable toda la telemetría y eventos de conducción obtenidos a través del SDK de Sentiance. Este esquema permite el análisis posterior de patrones de manejo, la calificación de usuarios (scoring), y la integración con modelos de negocio de aseguradoras (ej. IKE) para evaluación de riesgos, basándose en trayectos verificados, roles de los ocupantes e incidentes geolocalizados.

Note

**Diferencias Clave con el Diseño Original de IKE:**

1. Todas las tablas finales incluyen campos internos de auditoría/ingesta que no existían en el diseño original: IdOffload y FechaOffload.  
2. Se han descartado de esta documentación las tablas intermedias ("staging tables" como MovDebug\_Eventos y SentianceEventos) ya que son exclusivas del pipeline temporal de procesamiento y no almacenan datos definitivos para consumo.  
3. Tipos de datos estandarizados al formato SQL Server (nvarchar, float, datetime, text).

---

## **Diccionario de Datos**

A continuación se detalla la estructura **real y definitiva** de las tablas implementadas en Microsoft SQL Server, incluyendo la descripción de cada columna.

### **1\. Tabla: Transporte**

La información para completar esta tabla se puede obtener a partir de dos tipos de evento: DrivingInsights para los desplazamientos que los generan (CAR, MOTOCYCLE y BUS) o de UserContextUpdate con con criteria CURRENT\_EVENT para el resto.

| Columna SQL | Tipo de Dato | Descripción | Observaciones |
| :---- | :---- | :---- | :---- |
| IdOffload | int | Log de ingesta del bucket/lote. | **Discontinuado** |
| FechaOffload | date | Fecha de procesamiento local en la BD. | **Discontinuado** |
| usuario | nvarchar | Identificador del usuario Sentiance | Id de Sentiance |
| viaje | nvarchar | Identificador único del viaje (UUID). | `Ver abajo` |
| modo\_transporte | nvarchar | Medio de transporte inferido |  (ej. Auto, Caminando, Colectivo, Moto, Subte, Desconocido, Tren, RUNNING, Bicicleta). |
| comienzo | datetime | Fecha y hora de inicio del viaje. | `Ver abajo` |
| fin | datetime | Fecha y hora de fin del viaje. | `Ver abajo` |
| duracion | int | Duración total del viaje en segundos. | `Ver abajo` |
| metadata | text | Metadatos adicionales; contenedor para payloads JSON. | Por el momento está todo en \[\] |
| velocidad\_maxima | float | Velocidad máxima alcanzada durante el viaje. | Por el momento está todo en \-1 |

Para los registros con DrivingInsight:  
`{`  
  `"safetyScores": { ... },`  
  `"transportEvent": {`  
    `"id": "0266f544-4a35-4971-94ce-5e5c04982d31",   // Path: $.transportEvent.id`  
    `"transportMode": "CAR",`  
    `"startTime": "2025-10-04T08:20:40.128-0300",    // Path: $.transportEvent.startTime`  
    `"endTime": "2025-10-04T08:32:58.128-0300",      // Path: $.transportEvent.endTime`  
    `"durationInSeconds": 738,                       // Path: $.transportEvent.durationInSeconds`  
    `"occupantRole": "PASSENGER",`  
    `...`  
  `}`  
`}`

Para los registros de tipo userContextUpdate (donde el criterio es CURRENT\_EVENT), la información de los viajes se encuentra dentro del objeto userContext, específicamente en el array de events.

`{`  
  `"criteria": ["CURRENT_EVENT"],`  
  `"userContext": {`  
    `"events": [`  
      `{`  
        `"type": "IN_TRANSPORT",`  
        `"id": "8e561fb6-ec18-49ed-ad3e-66e5afe8e6a0",         // Path: $.userContext.events[0].id`  
        `"transportMode": "MOTORCYCLE",                       // Path: $.userContext.events[0].transportMode`  
        `"startTime": "2025-10-03T21:28:38.971-0300",         // Path: $.userContext.events[0].startTime`  
        `"endTime": "2025-10-03T21:35:32.971-0300",           // Path: $.userContext.events[0].endTime`  
        `"durationInSeconds": 414,                            // Path: $.userContext.events[0].durationInSeconds`  
        `"occupantRole": "UNAVAILABLE",`  
        `"isProvisional": false,`  
        `...`  
      `},`  
      `{ ... } // Otros eventos (STATIONARY, etc.)`  
    `],`  
    `"semanticTime": "NIGHT",`  
    `...`  
  `}`  
`}`

**OJO\!\!\!\! Que pueden venir varios recorridos en un solo JSON**. Se deberían extraer sólo los que no corresponden a CAR, MOTOCYCLE y BUS. Pienso que habría que descartar los que no tienen waypoints pero, por ahora, yo los dejaría para debugging.  
Creo que los provisionales sí podrían ser descartados.

---

### **2\. Tabla: Recorridos**

Maneja la información geoespacial de la ruta trazada por el dispositivo móvil.

| Columna SQL | Tipo de Dato | Descripción | Observaciones |
| :---- | :---- | :---- | :---- |
| IdOffload | int | Log de ingesta del bucket/lote. | **Discontinuado** |
| FechaOffload | date | Fecha de procesamiento local. | **Discontinuado** |
| usuario | nvarchar | Identificador del usuario Sentiance | Id de Sentiance |
| viaje | nvarchar | Identificador único del viaje. | Ver la explicación en la tabla Transporte, más arriba  |
| distancia\_m | float | Distancia total recorrida en metros. | `Ver abajo` |
| polyline | text | Recorrido codificado geomorfológicamente. | De acuerdo con lo hablado con Mitul la forma actualizada de obtener las trayectorias es a partir de los waypoints.  Ver abajo un ejemplo de código para pasar de waypoints a polyline |
| puntos\_recorrido | text | Lista JSON de puntos crudos con latitud/longitud. | Se puede usar el array de waypoints |
| ubicacion\_inicio | text | Ubicación inicial estimada (Lat/Lon). | Actualmente no se popula pero se puede obtener del array de waypoints (ver función más abajo) |
| ubicacion\_fin | text | Ubicación final estimada (Lat/Lon). | Actualmente no se popula pero se puede obtener del array de waypoints (ver función más abajo) |
| maxima\_velocidad | float | Máxima velocidad registrada en el trayecto. | Se puede obtener del array de waypoints (ver función más abajo) |

Para los registros de tipo DrivingInsights, la distancia se encuentra dentro del objeto transportEvent.

`{`  
  `"safetyScores": { ... },`  
  `"transportEvent": {`  
    `"id": "d40d2ea2-fcdc-4da6-9595-e75a6dab4685",`  
    `"distance": 2035,                       // Path: $.transportEvent.distance`  
    `"transportMode": "MOTORCYCLE",`  
    `"startTime": "...",`  
    `"endTime": "...",`  
    `"durationInSeconds": 414,`  
    `...`  
  `}`  
`}`

Para los trayectos en los registros de userContextUpdate, la distancia se encuentra dentro de cada objeto del array events.

`{`  
  `"criteria": ["CURRENT_EVENT"],`  
  `"userContext": {`  
    `"events": [`  
      `{`  
        `"type": "IN_TRANSPORT",`  
        `"id": "8e561fb6-ec18-49ed-ad3e-66e5afe8e6a0",`  
        `"distance": 132812,                // Path: $.userContext.events[i].distance`  
        `"transportMode": "CAR",`  
        `"startTime": "...",`  
        `"endTime": "...",`  
        `"durationInSeconds": 414,`  
        `...`  
      `}`  
    `]`  
  `}`  
`}`

`/**`  
 `* encodePolyline`  
 `* ==============`  
 `* Convierte un array de waypoints (formato Sentiance) al formato`  
 `* "Encoded Polyline Algorithm" de Google Maps.`  
 `*`  
 `* Además de la polyline codificada, devuelve el punto de INICIO`  
 `* y el punto de FIN del recorrido, extraídos del primer y último waypoint.`  
 `* También calcula la velocidad máxima registrada durante el recorrido.`  
 `*`  
 `* @param {Array} waypoints - Array de waypoints con { latitude, longitude, timestamp, speedInMps, ... }`  
 `* @returns {Object} {`  
 `*   encodedPolyline: string,  // Polyline codificada (Google format)`  
 `*   origin: { latitude, longitude, timestamp },       // Primer punto`  
 `*   destination: { latitude, longitude, timestamp },  // Último punto`  
 `*   maxSpeedMps: number,      // Velocidad máxima en m/s`  
 `*   maxSpeedKph: number,      // Velocidad máxima en km/h`  
 `* }`  
 `*`  
 `* Referencia algoritmo: https://developers.google.com/maps/documentation/utilities/polylinealgorithm`  
 `*/`  
`function encodePolyline(waypoints) {`

  `// ── PUNTOS DE INICIO Y FIN ─────────────────────────────────────────────────`  
  `// Extraemos el primer y último waypoint antes de procesar la polyline`  
  `const firstWaypoint = waypoints[0];`  
  `const lastWaypoint  = waypoints[waypoints.length - 1];`

  `const origin = {`  
    `latitude:  firstWaypoint.latitude,`  
    `longitude: firstWaypoint.longitude,`  
    `timestamp: firstWaypoint.timestamp,`  
  `};`

  `const destination = {`  
    `latitude:  lastWaypoint.latitude,`  
    `longitude: lastWaypoint.longitude,`  
    `timestamp: lastWaypoint.timestamp,`  
  `};`

  `// ── VELOCIDAD MÁXIMA ───────────────────────────────────────────────────────`  
  `// Recorremos todos los waypoints buscando el mayor valor de speedInMps`  
  `// Math.max con spread opera sobre el array de velocidades en una sola línea`  
  `const maxSpeedMps = Math.max(...waypoints.map(wp => wp.speedInMps ?? 0));`

  `// Convertimos a km/h para mayor legibilidad (1 m/s = 3.6 km/h)`  
  `const maxSpeedKph = parseFloat((maxSpeedMps * 3.6).toFixed(1));`

  `// ── CODIFICACIÓN DE LA POLYLINE ────────────────────────────────────────────`  
  `let encodedPolyline = '';`

  `// Guardamos la posición anterior para calcular deltas (diferencias)`  
  `// El algoritmo trabaja con coordenadas RELATIVAS al punto anterior,`  
  `// no con coordenadas absolutas`  
  `let prevLat = 0;`  
  `let prevLng = 0;`

  `for (const wp of waypoints) {`

    `// Procesamos latitud y longitud por separado, con la misma lógica`  
    `for (const [currentValue, previousValue] of [`  
      `[wp.latitude,  prevLat],`  
      `[wp.longitude, prevLng],`  
    `]) {`

      `// Paso 1: Calcular la diferencia respecto al punto anterior`  
      `// Multiplicamos por 1e5 y redondeamos (el algoritmo trabaja con`  
      `// enteros de 5 decimales de precisión)`  
      `let delta = Math.round(currentValue * 1e5) - Math.round(previousValue * 1e5);`

      `// Paso 2: Desplazar bits a la izquierda (x2)`  
      `// Si el valor es negativo, invertir todos los bits (~)`  
      `delta = delta < 0 ? ~(delta << 1) : (delta << 1);`

      `// Paso 3: Dividir en grupos de 5 bits y codificar cada chunk`  
      `// mientras haya más de 5 bits pendientes...`  
      `while (delta >= 0x20) {`  
        `// Tomar los 5 bits menos significativos, activar el bit 6 (0x20)`  
        `// y sumar 63 para que quede en rango ASCII imprimible`  
        `encodedPolyline += String.fromCharCode((0x20 | (delta & 0x1f)) + 63);`  
        `delta >>= 5; // descartar los 5 bits ya procesados`  
      `}`

      `// Último chunk (menos de 5 bits): solo sumar 63, sin activar bit 6`  
      `encodedPolyline += String.fromCharCode(delta + 63);`  
    `}`

    `// Actualizar posición anterior para el próximo waypoint`  
    `prevLat = wp.latitude;`  
    `prevLng = wp.longitude;`  
  `}`

  `// ── RESULTADO ──────────────────────────────────────────────────────────────`  
  `return {`  
    `encodedPolyline, // string listo para usar en Google Maps API`  
    `origin,          // primer punto del recorrido { latitude, longitude, timestamp }`  
    `destination,     // último punto del recorrido { latitude, longitude, timestamp }`  
    `maxSpeedMps,     // velocidad máxima en metros por segundo`  
    `maxSpeedKph,     // velocidad máxima en kilómetros por hora`  
  `};`  
`}`

`// ── EJEMPLO DE USO ─────────────────────────────────────────────────────────────`  
`const { encodedPolyline, origin, destination, maxSpeedMps, maxSpeedKph } = encodePolyline(event.waypoints);`

`console.log('Polyline:   ', encodedPolyline);`  
`console.log('Inicio:     ', origin);       // { latitude: -35.753, longitude: -58.500, timestamp: ... }`  
`console.log('Fin:        ', destination);  // { latitude: -35.754, longitude: -58.503, timestamp: ... }`  
`console.log('Vel. máx:  ', maxSpeedMps, 'm/s →', maxSpeedKph, 'km/h');`

---

### **3\. Tabla: Conduccion**

Define los atributos de rol (piloto vs pasajero) identificados mediante la IA de clasificación en la nube de Sentiance.

| Columna SQL | Tipo de Dato | Descripción | Observaciones |
| :---- | :---- | :---- | :---- |
| id | int | Clave primaria autonumérica de la tabla. | **\[NUEVO\]** (Identity). |
| registro | datetime | Momento de cálculo e inserción en base. | getdate() |
| usuario | nvarchar | Identificador de usuario. | Sentiance id |
| viaje | nvarchar | Identificador de viaje. | id del viaje |
| ocupante | varchar | Rol inferido (ej. DRIVER, PASSENGER). | occupantRole de DrivingInsights |

---

### **4\. Tabla: Eventos**

Actualmente los eventos vienen en driving\_events\_all.csv. Nosotros estamos sacando la información de los viajes a partir de DrivingInsights:

`interface DrivingInsights {`

  `transportEvent: TransportEvent  // ← está acá adentro`

  `safetyScores: SafetyScores`

`}`

que NO tiene la información de los eventos. Para obtenerla hay que pedirla explícitamente:

import drivingInsights from "@sentiance-react-native/driving-insights";

// 1\. Listener: avisa que el viaje terminó y los insights están listos

const subscription \= await drivingInsights.addDrivingInsightsReadyListener(

 async (insights) \=\> {

   const transportId \= insights.transportEvent.id;

   // 2\. Scores resumen (ya los tienes en  insights )

   const scores \= insights.safetyScores;

   console.log("Overall score:", scores.overallScore);

   console.log("Smooth score:", scores.smoothScore);

   console.log("Focus score:", scores.focusScore);

   console.log("Legal score:", scores.legalScore);

   console.log("Call while moving score:", scores.callWhileMovingScore);

   console.log("Harsh braking score:", scores.harshBrakingScore);

   console.log("Harsh turning score:", scores.harshTurningScore);

   console.log("Harsh acceleration score:", scores.harshAccelerationScore);

   console.log("Wrong way driving score:", scores.wrongWayDrivingScore);

   console.log("Attention score:", scores.attentionScore);

   // 3\. Detalle de eventos: llamadas separadas con el transportId

   const speedingEvents  \= await drivingInsights.getSpeedingEvents(transportId);


   // harshEvents incluye: ACCELERATION, BRAKING, TURN

   const harshEvents     \= await drivingInsights.getHarshDrivingEvents(transportId);\\

   const phoneEvents     \= await drivingInsights.getPhoneUsageEvents(transportId);

   // IMPORTANTE: getCallWhileMovingEvents está deprecado. Usar getCallEvents:

   const callEvents      \= await drivingInsights.getCallEvents(transportId);

   // NUEVO: Conducción en sentido contrario

   const wrongWayEvents  \= await drivingInsights.getWrongWayDrivingEvents(transportId);

   console.log(\`Eventos recuperados para el transportId ${transportId}\`);

 }

);

Para simplificar el envío de toda la info al backend se propone empaquetarla en una estructura de tipo`:`

import {  
 TransportEvent,  
 SafetyScores,  
 HarshDrivingEvent,  
 SpeedingEvent,  
 PhoneUsageEvent,  
 CallEvent, // \<- Recomendado (en vez de CallWhileMovingEvent)  
 WrongWayDrivingEvent // \<- Recomendado agregarlo  
} from "@sentiance-react-native/driving-insights";  
export interface TripInfo {  
 // ── DATOS DEL VIAJE ──────────────────────────────────────  
 // transportEvent: id, modo, duración, distancia, isProvisional, waypoints, etc.  
 transportEvent: TransportEvent;      
 // ── SCORES RESUMEN ───────────────────────────────────────  
 // safetyScores: overall, smooth, focus, legal, etc...  
 safetyScores: SafetyScores;          
 // ── EVENTOS DETALLADOS ───────────────────────────────────  
 // harshDrivingEvents: Tipo ACCELERATION, BRAKING o TURN  
 harshDrivingEvents: HarshDrivingEvent\[\];      
  // speedingEvents: Excesos de velocidad  
 speedingEvents: SpeedingEvent\[\];              
  // phoneUsageEvents: Uso activo del teléfono en general  
 phoneUsageEvents: PhoneUsageEvent\[\];          
  // callEvents: NUEVA ESTRUCTURA de llamadas (Reemplaza a CallWhileMovingEvent)   
 callEvents: CallEvent\[\];  
 // wrongWayEvents: NUEVO: Conducción en contramano (Poco frecuente pero existe)  
 wrongWayEvents?: WrongWayDrivingEvent\[\];  
}

Y enviarla de la misma forma en que actualmente se envía DrivingInsights

| Columna SQL | Tipo de Dato | Descripción | Observaciones |
| :---- | :---- | :---- | :---- |
| IdOffload | int | Log de ingesta del bucket/lote. | **Discontinuado** |
| FechaOffload | date | Fecha de procesamiento local. | **Discontinuado** |
| usuario | nvarchar | Identificador de usuario. | Sentiance id |
| viaje | nvarchar | Identificador de viaje. | Id del viaje |
| aceleracion | text | Lista JSON de aceleraciones. | Consolida múltiples filas en un simple array/objeto. |
| uso\_telefono | text | Eventos registrados sobre uso general de teléfono móvil. |  |
| curvas | text | Detalles de curvas bruscas tomadas. | Equivalente adaptado a text. |
| celular\_fijo | text | Interacciones con el teléfono cuando estaba fijo en soporte. | Están todos en \[\] |
| frenado | text | Lista JSON de frenadas. | Equivalente adaptado a text. |
| exceso\_de\_velocidad | text | Registros desglosados de excesos de velocidad. | **\[REEMPLAZA\]** Se corrigió el nombre de columna para coincidir con el original \`exceso_de_velocidad\`. |
| llamados | text | Eventos JSON de llamadas de voz detectadas. | Equivalente adaptado a text. |
| pantalla | text | Detalles sobre toques o iteracción con la pantalla del celular. | Están todos en \[\] |

---

### **5\. Tabla: EventosSignificantes**

Por ahora se podría repetir la info que se pone en Eventos, hasta que se defina cómo establecer y criterios.

| Columna SQL | Tipo de Dato | Descripción | Observaciones |
| :---- | :---- | :---- | :---- |
| IdOffload | int | Log de ingesta del bucket/lote. | **Discontinuado** |
| FechaOffload | date | Fecha de procesamiento local. | **Discontinuado** |
| usuario | nvarchar | Identificador de usuario. |  |
| viaje | nvarchar | Identificador de viaje. |  |
| aceleracion | text | Lista JSON de aceleraciones verdaderamente fuertes. |  |
| uso\_telefono | text | Eventos registrados sobre uso severo del teléfono móvil. |  |
| curvas | text | Detalles de curvas extremadamente bruscas tomadas gravadas. |  |
| celular\_fijo | text | Interacciones severas y prolongadas en soporte. |  |
| frenado | text | Lista JSON de frenadas críticas de asfalto. |  |
| exceso\_velocidad | text | Registros desglosados de excesos de alta velocidad continuos. |  |
| llamados | text | Llamadas distraídas con factor multiriesgo. |  |
| pantalla | text | Iteracción grave in-transit. |  |

---

### **6\. Tabla: PuntajesPrirmariosTr**

Se obtienen desde el objeto safetyScores interno a DrivingInsights.

| Columna SQL | Tipo de Dato | Descripción | Observaciones |
| :---- | :---- | :---- | :---- |
| IdOffload | int | Log de ingesta del bucket/lote. | **Discontinuado** |
| FechaOffload | date | Fecha de procesamiento local. | **Discontinuado** |
| usuario | nvarchar | Identificador de usuario de Sentiance |  |
| viaje | nvarchar | Identificador de viaje. |  |
| legal | float | Puntuación de legalidad ("legalScore"). | legalScore de DrivingInsights |
| suavidad | float | Puntuación global de suavidad ("smoothScore"). | smoothScore de DrivingInsights |
| atencion | float | Puntuación global de atención ("focusScore"). | focusScore de DrivingInsights |
| promedio | float | Media o puntuación final consolidada ("overallScore"). | loverallScore de DrivingInsights |

   `"safetyScores": {`  
       `"harshTurningScore": 1,`  
       `"harshBrakingScore": 1,`  
       `"legalScore": 1,`  
       `"overallScore": 0.83621299266815186,`  
       `"callWhileMovingScore": 1,`  
       `"focusScore": 0.50863897800445557,`  
       `"harshAccelerationScore": 1,`  
       `"smoothScore": 1`  
   `},`

---

### **7\. Tabla: PuntajesSecundariosTr**

Almacena las sub-métricas o deméritos algorítmicos específicos del viaje. Estos explican por qué bajaron los "Puntajes Primarios".

| Columna SQL | Tipo de Dato | Descripción | Observaciones |
| :---- | :---- | :---- | :---- |
| IdOffload | int | Log de ingesta del bucket/lote. | **Discontinuado** |
| FechaOffload | date | Fecha de procesamiento local. | **Discontinuado** |
| usuario | nvarchar | Identificador de usuario de Sentiance |  |
| viaje | nvarchar | Identificador de viaje. |  |
| concentracion | float | Puntuación de concentración, relacionada a llamadas. | Es identifica a PuntajesPrirmariosTr.atencion |
| aceleracion\_fuerte | float | Penalidad numérica por aceleraciones violentas. | \-1 |
| frenado\_fuerte | float | Penalidad numérica por frenados bruscos excesivos. | \-1 |
| curvas\_fuertes | float | Penalidad numérica debido a giros fuertes. | \-1 |
| anticipacion | float | Sub-puntuación de la anticipación del chofer al frenar/acelerar. | \-1 |
| celular\_fijo | int | Penalización global por el uso de celular fijo validada en número. | \-1 |
| eventos\_fuertes | int | Penalización agregada / cuenta global referida a eventos violentos. | **Ver pestáña bug porque hay que corregirlo**  harsh\_events del CSV se está redondeando a 1 ó 0 y se guarda en eventos\_fuertes  de PuntajesSecundariosTr (también hay muchos casos con \-1). [https://docs.sentiance.com/sentiance-insights/overview-of-sentiance-insights/driving-insights/driving-events-and-scores](https://docs.sentiance.com/sentiance-insights/overview-of-sentiance-insights/driving-insights/driving-events-and-scores) Todo parece indicar que es un cálculo del backend. Le mando la consulta a Mitul: [https://sentiance.slack.com/archives/C09ECDR1WJX/p1770134986293669](https://sentiance.slack.com/archives/C09ECDR1WJX/p1770134986293669) Hi @Claudio The harsh event is a combination of harsh acceleration, harsh braking, and harsh turning. This event was a legacy metric, as we did not have individual scores in our previous on-device solution. Now, we have all of them as separate scores. |

### **8\. Tabla: ChoqueDeVehiculo**

Almacena eventos específicos de colisión vehicular detectados por el sistema de IA integral.

| Columna SQL | Tipo de Dato | Descripción | Observaciones |
| :---- | :---- | :---- | :---- |
| Id | int | Clave  primaria autonumérica. |  |
| Registro | datetime | Fecha de recepción en base de datos. |  |
| EventoId | int | Referencia al ID del evento. |  |
| usuario | varchar | Identificador del usuario. | . |
| LeidoFechaHora | datetime | Marca de tiempo de lectura. |  |
| json | varchar | Payload en bruto con los detalles de telemetría pre-choque y post-choque. |  |

---

### **9\. Tabla: PerfilDeUsuario**

Almacena y mantiene el perfil, historial semántico y predicciones asociadas a patrones de rutina del usuario.

| Columna SQL | Tipo de Dato | Descripción | Observaciones |
| :---- | :---- | :---- | :---- |
| Id | int | Llave primaria autonumérica. |  |
| Registro | datetime | Fecha de recepción/actualización del perfil. |  |
| EventoId | int | Referencia al evento o batch asociado. |  |
| usuario | varchar | Identificador único del usuario global. |  |
| LeidoFechaHora | datetime | Marca de tiempo de lectura u orquestación. |  |
| json | varchar | Payload con el perfil extendido arrojado por el SDK. |  |

---

