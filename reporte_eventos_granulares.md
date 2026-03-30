# Informe de Eventos Granulares - SentianceEventos

Este documento contiene un desglose de los registros que disponen de datos granulares (frenadas, aceleraciones, uso de teléfono y excesos de velocidad) en la base de datos SQL.


| ID Registro | Tipo de Evento | Fecha y Hora     | Transport ID (Viaje)                 | Sentiance ID (Conductor) | Detalles Relevantes                    | Encontrado en CSV (Local)   |
| ----------- | -------------- | ---------------- | ------------------------------------ | ------------------------ | -------------------------------------- | --------------------------- |
| 31507       | PhoneEvents    | 2026-03-10 17:13 | 3a394798-4953-4003-a539-116cdd5bfee2 | 6996f737336ca008000000bf | NO_CALL (4 subtramos)                  | No encontrado (Fecha Mar10) |
| 29913       | PhoneEvents    | 2026-03-05 12:52 | 25f7c669-dc12-4961-81ae-53d7c2f90d5b | 6980bacfbfdfd0080000fc6c | NO_CALL (3 subtramos)                  | Sí (csv_20260305)           |
| 29912       | HarshEvents    | 2026-03-05 12:52 | 25f7c669-dc12-4961-81ae-53d7c2f90d5b | 6980bacfbfdfd0080000fc6c | ACCELERATION (Mag: 2.84, Conf: 80%)    | Sí (csv_20260305)           |
| 29907       | HarshEvents    | 2026-03-05 12:04 | 116eb2ed-7e45-4d07-8744-43fb93e4ebd0 | 6980bacfbfdfd0080000fc6c | BRAKING (Mag: 3.44), ACCEL (Mag: 3.72) | Sí (csv_20260305)           |
| 29901       | SpeedingEvents | 2026-03-05 11:43 | be9dc7de-d02b-4927-87b0-38bbb80c5c35 | 6980bacfbfdfd0080000fc6c | Vel: 12.97 m/s                         | Sí (csv_20260305)           |
| 29902       | HarshEvents    | 2026-03-05 11:43 | be9dc7de-d02b-4927-87b0-38bbb80c5c35 | 6980bacfbfdfd0080000fc6c | ACCELERATION (Mag: 2.76, Conf: 78%)    | Sí (csv_20260305)           |
| 29903       | PhoneEvents    | 2026-03-05 11:43 | be9dc7de-d02b-4927-87b0-38bbb80c5c35 | 6980bacfbfdfd0080000fc6c | NO_CALL                                | Sí (csv_20260305)           |
| 29833       | PhoneEvents    | 2026-03-05 08:00 | 724b2258-5372-40d0-9314-3f2ba259c3bf | 6996f737336ca008000000bf | NO_CALL                                | Sí (csv_20260305)           |
| 29772       | PhoneEvents    | 2026-03-04 19:28 | b79cf57c-0cc2-4451-95ed-630ca2d77d87 | 6996f737336ca008000000bf | NO_CALL (Múltiples eventos)            | Sí (csv_20260304)           |
| 29768       | PhoneEvents    | 2026-03-04 16:37 | 4fb922c8-7bff-4109-b3ff-0421131bc15d | 6996f737336ca008000000bf | NO_CALL (Subtramos largos)             | Sí (transports.csv)         |
| 29892       | HarshEvents    | 2026-03-04 14:20 | 0daad29a-7162-45d2-95a6-3acf6fada622 | 6980bacfbfdfd0080000fc6c | ACCELERATION (Mag: 2.78, Conf: 47%)    | Sí (csv_20260304)           |
| 29885       | SpeedingEvents | 2026-03-04 13:32 | b6c540b3-9876-41ce-8531-ed448d2ccde7 | 6980bacfbfdfd0080000fc6c | Vel: 12.94 m/s                         | Sí (csv_20260304)           |
| 29886       | HarshEvents    | 2026-03-04 13:32 | b6c540b3-9876-41ce-8531-ed448d2ccde7 | 6980bacfbfdfd0080000fc6c | ACCELERATION (Mag: 2.67, Conf: 53%)    | Sí (csv_20260304)           |
| 29887       | PhoneEvents    | 2026-03-04 13:32 | b6c540b3-9876-41ce-8531-ed448d2ccde7 | 6980bacfbfdfd0080000fc6c | NO_CALL (5 eventos)                    | Sí (csv_20260304)           |
| 29705       | HarshEvents    | 2026-03-04 13:25 | 1e280a36-aa6c-4da2-93c9-3d0f7e06a64c | 6996f737336ca008000000bf | ACCELERATION (Mag: 2.58)               | Sí (csv_20260304)           |
| 29701       | PhoneEvents    | 2026-03-04 13:15 | d5abe0d9-bd85-4d8b-ad24-e04aaedaa81c | 6996f737336ca008000000bf | NO_CALL                                | Sí (csv_20260304)           |
| 29649       | PhoneEvents    | 2026-03-04 10:07 | 8d607531-eb8c-4959-9d99-d47a7e6ce4cb | 6996f737336ca008000000bf | NO_CALL (Múltiples subtramos)          | Sí (csv_20260304)           |
| 29674       | SpeedingEvents | 2026-03-03 22:19 | dc4b2584-2c58-4071-b234-ac4bb83caf43 | 6980bacfbfdfd0080000fc6c | Múltiples excesos (Máx 22.4 m/s)       | Sí (csv_20260304)           |
| 29675       | HarshEvents    | 2026-03-03 22:19 | dc4b2584-2c58-4071-b234-ac4bb83caf43 | 6980bacfbfdfd0080000fc6c | BRAKING (Mag: 3.28), ACCEL x3          | Sí (csv_20260304)           |
| 29676       | PhoneEvents    | 2026-03-03 22:19 | dc4b2584-2c58-4071-b234-ac4bb83caf43 | 6980bacfbfdfd0080000fc6c | NO_CALL (5 eventos)                    | Sí (csv_20260304)           |


> [!NOTE]
> Esta tabla muestra una selección de los registros más recientes procesados con éxito en la base de datos SQL.  
> Se observa que el procesamiento masivo de estos eventos comenzó el **1 de Marzo de 2026**.