| Nodo | Explicación conceptual del contenido |
| :--- | :--- |
| **SentianceEventos** | Tabla raw de aterrizaje de todos los registros Sentiance; es el stream de entrada antes de normalizar. Se podría purgar regularmente ya que `SdkSourceEvent` quedaría como referencia de origen. |
| **SdkSourceEvent** | Registro de procedencia de cada evento fuente ya normalizado. |
| **TimelineEventHistory** | Historial de eventos de EventTimeline; puede incluir UNKNOWN, STATIONARY, OFFTHEGRID e INTRANSPORT. Los transportes pueden traer modo, distancia, waypoints, tags, occupant role e isProvisional. |
| **UserContextPayload** | Se alimenta de los eventos donde Sentiance devuelve un objeto `UserContext` (ej. `requestUserContext` o listeners de actualización). |
| **Trip** | Tabla canónica de viajes o transportes en el modelo, que consolida evidencia de transporte desde timeline, user context y driving insights. |
| **DrivingInsightsTrip** | Registro de driving insights para un transporte completado, combinando el `transportEvent` asociado y los `safetyScores`. |
| **DrivingInsightsHarshEvent** | Evento hijo que representa maniobras bruscas (aceleración, frenado o giro) con tiempo, waypoints, magnitud y confianza. |
| **DrivingInsightsPhoneEvent** | Evento hijo de uso de teléfono durante un transporte, con inicio, fin y waypoints. |
| **DrivingInsightsCallEvent** | Evento hijo de call-while-moving, con tiempos, waypoints y velocidades mínima/máxima. |
| **DrivingInsightsSpeedingEvent** | Evento hijo que representa períodos de exceso de velocidad durante un transporte completado. |
| **DrivingInsightsWrongWayDrivingEvent** | Evento hijo que representa segmentos de conducción en sentido contrario. |
| **VehicleCrashEvent** | Evento de choque detectado con tiempo, ubicación, magnitud, velocidad al impacto, delta-V, confianza y severidad. |
| **SdkStatusHistory** | Historial de snapshots del estado del SDK, como permisos o estado operativo. |
| **UserActivityHistory** | Resúmenes de actividad del usuario (`TRIP`, `STATIONARY`, `UNKNOWN`) obtenidos vía API o listeners. Vista resumida para dashboards rápidos. (Parece que no se están recibiendo actualmente en el webhook de eventos). |
| **TechnicalEventHistory** | Historial de eventos técnicos u operativos, como logs, offload o señales de soporte del pipeline. |
| **UserContextEventHistory** | Desglosa el array `events`. Alimenta a `Trip` cuando son `STATIONARY` o `IN_TRANSPORT` (útil para trayectorias sin `DrivingInsights`). |
| **UserContextActiveSegmentHistory** | Desglosa el array `activeSegments` al que pertenece el usuario. |
| **UserContextSegmentAttribute** | Tabla hija para los atributos de cada segmento activo (nombre/valor). |
| **UserHomeHistory** | Guarda la información del venue "Casa" si venía en el payload de contexto. |
| **UserWorkHistory** | Guarda la información del venue "Trabajo" si venía en el payload de contexto. |
| **UserContextUpdateCriteria** | Guarda los motivos por los cuales se actualizó el contexto. |