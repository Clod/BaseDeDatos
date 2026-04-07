## Segmentos (`Segment`)

El concepto central de Lifestyle Insights son los segmentos, que clasifican comportamientos del usuario. Cada segmento tiene: 

- `**category**`: `LEISURE` (Ocio), `MOBILITY` (Movilidad), `WORK_LIFE` (Vida laboral)
- `**subcategory**`: `COMMUTE` (Desplazamiento al trabajo), `DRIVING` (Conducción), `ENTERTAINMENT` (Entretenimiento), `FAMILY` (Familia), `HOME` (Hogar), `SHOPPING` (Compras), `SOCIAL` (Social), `TRANSPORT` (Transporte), `TRAVEL` (Viajes), `WELLBEING` (Bienestar), `WINING_AND_DINING` (Gastronomía), `WORK` (Trabajo)
- `**type**`: el perfil específico detectado

### Segmentos por categoría

**MOBILITY**: 


| Tipo                       | Traducción                              | Descripción                               |
| -------------------------- | --------------------------------------- | ----------------------------------------- |
| Die Hard Driver            | Conductor empedernido                   | Usa el auto para casi todos los viajes    |
| Easy Commuter              | Viajero tranquilo                       | Tiene un trayecto fácil al trabajo        |
| Frequent Flyer             | Viajero frecuente                       | Vuela frecuentemente                      |
| Green Commuter             | Viajero ecológico                       | Se mueve principalmente caminando/en bici |
| Heavy Commuter             | Viajero intensivo                       | Tiene un trayecto pesado al trabajo       |
| Long Commuter              | Viajero de larga distancia              | Vive lejos del trabajo                    |
| Normal Commuter            | Viajero normal                          | Tiempo y distancia de viaje promedio      |
| Public Transports User     | Usuario de transporte público           | Usa transporte público frecuentemente     |
| Public Transports Commuter | Usuario de transporte público (trabajo) | Comunica con transporte público           |
| Short Commuter             | Viajero de corta distancia              | Vive cerca del trabajo                    |


**WORKLIFE**: 


| Tipo              | Traducción                   | Descripción                                             |
| ----------------- | ---------------------------- | ------------------------------------------------------- |
| Early Bird        | Madrugador                   | Primera actividad matutina más temprana que el promedio |
| Fulltime Worker   | Trabajador a tiempo completo | Trabaja a tiempo completo                               |
| Home Bound        | Vinculado al hogar           | Raramente sale de casa o viaja lejos                    |
| Homebody          | Hogareño                     | Prefiere quedarse en casa en fines de semana            |
| Homeworker        | Teletrabajador               | Trabaja desde casa o está desempleado                   |
| Late Worker       | Trabajador nocturno          | Trabaja hasta tarde                                     |
| Night Owl         | Ave nocturna                 | Última actividad vespertina más tarde que el promedio   |
| Nightworker       | Trabajador de noche          | Trabaja de noche                                        |
| Parttime Worker   | Trabajador a tiempo parcial  | Trabaja a tiempo parcial                                |
| Sleep Deprived    | Con falta de sueño           | Duerme muy poco                                         |
| Student           | Estudiante                   | Estudiante o docente                                    |
| Uber Parent       | Super padre/madre            | Lleva a sus hijos al colegio/jardín                     |
| Work Life Balance | Equilibrio trabajo-vida      | Buen equilibrio entre trabajo y vida personal           |
| Work Traveller    | Viajero de negocios          | Trabaja mucho en entornos remotos o viajando            |
| Workaholic        | Adicto al trabajo            | Trabaja más de lo promedio                              |


**LEISURE**: 


| Tipo           | Traducción                 | Descripción                                                         |
| -------------- | -------------------------- | ------------------------------------------------------------------- |
| Bar Goer       | Asiduo concurrente a bares | Disfruta de las salidas nocturnas en pubs o bares                   |
| Foodie         | Amante de la comida        | Entusiasta de la comida fresca, compra comida con frecuencia        |
| Healthy Biker  | Ciclista saludable         | Usa la bicicleta con frecuencia para largas distancias              |
| Healthy Walker | Caminante saludable        | Camina con frecuencia largas distancias                             |
| Nature Lover   | Amante de la naturaleza    | Le gusta ir a parques, jardines públicos, zoos o reservas naturales |
| Resto Lover    | Amante de restaurantes     | Le gusta comer fuera                                                |
| Shopaholic     | Comprador compulsivo       | Realiza compras con mucha frecuencia                                |
| Sportive       | Deportista                 | Practica deporte con regularidad                                    |


## Tiempo Semántico (`semanticTime`)

El `semanticTime` es personal y relativo al usuario, con los siguientes valores posibles: 

`UNKNOWN` (Desconocido) · `MORNING` (Mañana) · `LATE_MORNING` (Media mañana) · `LUNCH` (Almuerzo) · `AFTERNOON` (Tarde) · `EARLY_EVENING` (Atardecer) · `EVENING` (Noche) · `NIGHT` (Madrugada)

Esto permite saber, por ejemplo, cuándo es el momento adecuado para interactuar con el usuario (por ejemplo, enviar una notificación justo cuando sale del trabajo al mediodía). 

