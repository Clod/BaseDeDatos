## Segmentos (`Segment`)

El concepto central de Lifestyle Insights son los segmentos, que clasifican comportamientos del usuario. Cada segmento tiene: 

- `**category**`: `LEISURE`, `MOBILITY`, `WORKLIFE`
- `**subcategory**`: `COMMUTE`, `DRIVING`, `ENTERTAINMENT`, `FAMILY`, `HOME`, `SHOPPING`, `SOCIAL`, `TRANSPORT`, `TRAVEL`, `WELLBEING`, `WININGANDDINING`, `WORK`
- `**type**`: el perfil específico detectado
- `**attributes**`: lista de atributos con nombre y valor numérico

### Segmentos por categoría

**MOBILITY**: 


| Tipo                       | Traducción                              | Descripción                               | Identificador                                 |
| -------------------------- | --------------------------------------- | ----------------------------------------- | --------------------------------------------- |
| Die Hard Driver            | Conductor empedernido                   | Usa el auto para casi todos los viajes    | `mobility.driving.dieharddriver`              |
| Easy Commuter              | Viajero tranquilo                       | Tiene un trayecto fácil al trabajo        | `mobility.commute.easycommuter`               |
| Frequent Flyer             | Viajero frecuente                       | Vuela frecuentemente                      | `mobility.travel.frequentflyer`               |
| Green Commuter             | Viajero ecológico                       | Se mueve principalmente caminando/en bici | `mobility.commute.greencommuter`              |
| Heavy Commuter             | Viajero intensivo                       | Tiene un trayecto pesado al trabajo       | `mobility.commute.heavycommuter`              |
| Long Commuter              | Viajero de larga distancia              | Vive lejos del trabajo                    | `mobility.commute.longcommuter`               |
| Normal Commuter            | Viajero normal                          | Tiempo y distancia de viaje promedio      | `mobility.commute.normalcommuter`             |
| Public Transports User     | Usuario de transporte público           | Usa transporte público frecuentemente     | `mobility.transport.publictransportsuser`     |
| Public Transports Commuter | Usuario de transporte público (trabajo) | Comunica con transporte público           | `mobility.transport.publictransportscommuter` |
| Short Commuter             | Viajero de corta distancia              | Vive cerca del trabajo                    | `mobility.commute.shortcommuter`              |


**WORKLIFE**: 


| Tipo              | Traducción                   | Descripción                                             | Identificador                   |
| ----------------- | ---------------------------- | ------------------------------------------------------- | ------------------------------- |
| Early Bird        | Madrugador                   | Primera actividad matutina más temprana que el promedio | `worklife.home.earlybird`       |
| Fulltime Worker   | Trabajador a tiempo completo | Trabaja a tiempo completo                               | `worklife.work.fulltimeworker`  |
| Home Bound        | Vinculado al hogar           | Raramente sale de casa o viaja lejos                    | `worklife.home.homebound`       |
| Homebody          | Hogareño                     | Prefiere quedarse en casa en fines de semana            | `worklife.home.homebody`        |
| Homeworker        | Teletrabajador               | Trabaja desde casa o está desempleado                   | `worklife.work.homeworker`      |
| Late Worker       | Trabajador nocturno          | Trabaja hasta tarde                                     | `worklife.work.lateworker`      |
| Night Owl         | Ave nocturna                 | Última actividad vespertina más tarde que el promedio   | `worklife.home.nightowl`        |
| Nightworker       | Trabajador de noche          | Trabaja de noche                                        | `worklife.work.nightworker`     |
| Parttime Worker   | Trabajador a tiempo parcial  | Trabaja a tiempo parcial                                | `worklife.work.parttimeworker`  |
| Sleep Deprived    | Con falta de sueño           | Duerme muy poco                                         | `worklife.home.sleepdeprived`   |
| Student           | Estudiante                   | Estudiante o docente                                    | `worklife.work.student`         |
| Uber Parent       | Super padre/madre            | Lleva a sus hijos al colegio/jardín                     | `worklife.family.uberparent`    |
| Work Life Balance | Equilibrio trabajo-vida      | Buen equilibrio entre trabajo y vida personal           | `worklife.home.worklifebalance` |
| Work Traveller    | Viajero de negocios          | Trabaja mucho en entornos remotos o viajando            | `worklife.work.worktraveller`   |
| Workaholic        | Adicto al trabajo            | Trabaja más de lo promedio                              | `worklife.work.workaholic`      |


**LEISURE** incluye tipos como `BARGOER`, `FOODIE`, `HEALTHY_BIKER`, `HEALTHY_WALKER`, `NATURE_LOVER`, `RESTO_LOVER`, `SHOPAHOLIC` y `SPORTIVE`. 

## Tiempo Semántico (`semanticTime`)

El `semanticTime` es personal y relativo al usuario, con los siguientes valores posibles: 

`UNKNOWN` · `MORNING` · `LATEMORNING` · `LUNCH` · `AFTERNOON` · `EARLYEVENING` · `EVENING` · `NIGHT`

Esto permite saber, por ejemplo, cuándo es el momento adecuado para interactuar con el usuario (por ejemplo, enviar una notificación justo cuando sale del trabajo al mediodía). 

## Atributos del Segmento

Cada segmento puede tener atributos asociados con dos campos: [ppl-ai-file-upload.s3.amazonaws](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/collection_edddc53a-a68e-4979-b222-14696b40f15f/e19497ec-bade-4300-a198-28161a191ee2/Driving-Lifestyle-insights-data-dictionary.xlsx)

- `**name**`: método de cálculo del valor
- `**value**`: valor del atributo (numérico)