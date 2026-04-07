## Segmentos (`Segment`)

El concepto central de Lifestyle Insights son los segmentos, que clasifican comportamientos del usuario. Cada segmento tiene: 

- `**category**`: `LEISURE` (Ocio), `MOBILITY` (Movilidad), `WORK_LIFE` (Vida laboral)
- `**subcategory**`: `COMMUTE` (Desplazamiento al trabajo), `DRIVING` (Conducción), `ENTERTAINMENT` (Entretenimiento), `FAMILY` (Familia), `HOME` (Hogar), `SHOPPING` (Compras), `SOCIAL` (Social), `TRANSPORT` (Transporte), `TRAVEL` (Viajes), `WELLBEING` (Bienestar), `WINING_AND_DINING` (Gastronomía), `WORK` (Trabajo)
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


**LEISURE**: 


| Tipo           | Traducción                 | Descripción                                                         | Identificador                           |
| -------------- | -------------------------- | ------------------------------------------------------------------- | --------------------------------------- |
| Bar Goer       | Asiduo concurrente a bares | Disfruta de las salidas nocturnas en pubs o bares                   | `leisure.entertainment.bar_goer`        |
| Foodie         | Amante de la comida        | Entusiasta de la comida fresca, compra comida con frecuencia        | `leisure.shopping.foodie`               |
| Healthy Biker  | Ciclista saludable         | Usa la bicicleta con frecuencia para largas distancias              | `leisure.wellbeing.healthy_biker`       |
| Healthy Walker | Caminante saludable        | Camina con frecuencia largas distancias                             | `leisure.wellbeing.healthy_walker`      |
| Nature Lover   | Amante de la naturaleza    | Le gusta ir a parques, jardines públicos, zoos o reservas naturales | `leisure.entertainment.nature_lover`    |
| Resto Lover    | Amante de restaurantes     | Le gusta comer fuera                                                | `leisure.wining_and_dining.resto_lover` |
| Shopaholic     | Comprador compulsivo       | Realiza compras con mucha frecuencia                                | `leisure.shopping.shopaholic`           |
| Sportive       | Deportista                 | Practica deporte con regularidad                                    | `leisure.wellbeing.sportive`            |


## Tiempo Semántico (`semanticTime`)

El `semanticTime` es personal y relativo al usuario, con los siguientes valores posibles: 

`UNKNOWN` (Desconocido) · `MORNING` (Mañana) · `LATE_MORNING` (Media mañana) · `LUNCH` (Almuerzo) · `AFTERNOON` (Tarde) · `EARLY_EVENING` (Atardecer) · `EVENING` (Noche) · `NIGHT` (Madrugada)

Esto permite saber, por ejemplo, cuándo es el momento adecuado para interactuar con el usuario (por ejemplo, enviar una notificación justo cuando sale del trabajo al mediodía). 

