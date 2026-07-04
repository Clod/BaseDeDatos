# Suite de Regresión Golden-Snapshot

> **TL;DR** — Un corpus congelado de 170 eventos reales de producción se ejecuta a través
> del ETL real contra la BD Docker local; el estado resultante de las 24 tablas se compara
> byte a byte contra archivos golden bendecidos. Diff vacío = pasa.
> Diff no vacío = regresión o cambio intencional que hay que revisar y volver a bendecir.
> Nadie vuelve a verificar resultados a mano; los humanos (y los LLMs) solo miran *cambios*.

```bash
# El único comando (requiere BD Docker levantada; ELIMINA el VictaTMTK local):
.venv/bin/python3 -m pytest tests/regression --run-regression
```

---

## Tabla de Contenidos

1. [Filosofía](#1-filosofía)
2. [Cómo Funciona](#2-cómo-funciona)
3. [Inicio Rápido](#3-inicio-rápido)
4. [El Corpus](#4-el-corpus)
5. [Procedimientos](#5-procedimientos)
6. [La Suite de Invariantes](#6-la-suite-de-invariantes)
7. [El Contrato de Determinismo](#7-el-contrato-de-determinismo)
8. [Registro de Hallazgos](#8-registro-de-hallazgos)
9. [Límites y FAQ](#9-límites-y-faq)

---

## 1. Filosofía

El ETL es **determinista**: para un conjunto fijo de eventos de entrada existe exactamente
un estado de base de datos correcto. Ese único hecho dicta todo el diseño.

**Principio 1 — El diff supera al juicio.** Dado que la salida correcta es exactamente
especificable, la herramienta de verificación adecuada es una comparación byte a byte, no
una opinión. Un diff detecta un lat/lon invertido, una columna desfasada en uno, un
timestamp truncado en 22 en lugar de 23 caracteres — siempre, en milisegundos, gratis. Ni
releer a mano ni un juez LLM lo hace de forma confiable. Los LLMs están reservados para
los dos lugares donde el juicio realmente es necesario (ver Principio 4).

**Principio 2 — 100% datos reales, seleccionados por estructura.** Cada caso del corpus
es un evento de producción sin modificar. Los casos *no* se eligen a mano: la **forma
estructural** de un payload (el conjunto de rutas de claves JSON, incluyendo qué campos
llegaron como `null` explícito) se convierte en una huella digital, y el corpus conserva
exactamente un representante por forma por tipo de evento. Dos payloads con la misma forma
ejercen rutas de código idénticas (cada `.get()` se resuelve igual), por lo que esto da
cobertura estructural completa con ~1% del volumen: 18.556 eventos muestreados se reducen
a ~150 formas.

**Principio 3 — Sin datos sintéticos; los gaps se cierran solos.** Cuatro tipos de
eventos enrutados nunca han ocurrido en producción (ver §4). **No** fabricamos payloads
para ellos — un payload fabricado testea nuestra suposición, no el SDK. El gap está
documentado en `corpus/manifest.json`, y a medida que usuarios reales alimentan la base de
datos, el procedimiento de top-up (§5.4) cosecha representantes reales. Honestidad de
cobertura por encima del teatro de cobertura.

**Principio 4 — El blessing es el único juicio.** Declarar "esta salida es correcta"
ocurre una vez por cambio de comportamiento, en un diff de git revisado de `golden/`. El
*blessing inicial* es el único grande, y es ahí donde una auditoría LLM (§5.5) justifica
su existencia: verifica inputs contra filas golden contra la especificación de mapeo, para
que un humano solo resuelva discrepancias. Después del blessing, el LLM nunca vuelve a
intervenir — la suite es diff puro.

**Principio 5 — Dos capas, trabajos distintos.** El golden snapshot fija el comportamiento
exacto *para el corpus*. La suite de invariantes (§6) afirma verdades estructurales que
deben cumplirse para *cualquier* dato — ya detectó un bug de esquema en su primera
ejecución (§8). Los invariantes también corren en modo solo lectura contra producción.

---

## 2. Cómo Funciona

```
corpus/cases/*.json ──┐  (170 eventos reales congelados, cargados con sus ids)
                      ▼
        ┌──────────────────────────────┐
        │ 1. DROP + recrear VictaTMTK  │   development/sql/init_db.sql
        │ 2. INSERT corpus en          │   seeds de identity reseteados ⇒
        │    SentianceEventos          │   ids downstream deterministas
        │ 3. etl.run() hasta vaciar    │   SentianceETL real, bridge OFF
        │ 4. volcar las 24 tablas      │   normalización snapshot_lib.py
        │ 5. etl.run() una vez más     │   debe ser estrictamente no-op
        └──────────────────────────────┘
                      ▼
   volcado actual  ⟷  golden/*.jsonl   (commiteado, revisado, bendecido)
        más: consultas de invariantes, escenario de ordenamiento de huérfanos
```

| Archivo | Rol |
|---|---|
| `corpus/cases/*.json` | Eventos de entrada congelados (un archivo por caso, commiteado) |
| `corpus/manifest.json` | Resumen de cobertura + gaps documentados + orden de fuentes |
| `corpus/sources/*.json` | Pulls crudos de producción que alimentan el builder (commiteados) |
| `corpus_builder.py` | Selección por huella de forma + emparejamiento de padres |
| `fetch_topup.py` | Fetcher de producción solo lectura para top-ups del corpus |
| `snapshot_lib.py` | Volcado canónico: reglas de normalización + lista de tablas + diff |
| `harness.py` | Ciclo de vida de BD (guardia solo-localhost, reset de esquema, cargador) |
| `conftest.py` | El fixture de pipeline de sesión; congela volcados antes de correr tests |
| `test_snapshot.py` | Comparación golden + verificación de estado terminal; `--bless` |
| `test_idempotency.py` | Un segundo pass sobre la cola vaciada no debe cambiar nada |
| `test_orphan_ordering.py` | Hijo-antes-que-padre debe esperar, luego completarse |
| `test_reprocess.py` | Resetear `is_processed` y reprocesar no debe duplicar el subárbol DrivingInsights (MERGE + guardas `NOT EXISTS`) |
| `test_purge_reprocess.py` | `scripts/purge_for_reprocess.py` + reproceso: purga limpia y reconstrucción sin duplicados ni pérdidas |
| `test_invariants.py` | Verdades estructurales + verificación de drift de cobertura del snapshot |
| `golden/*.jsonl` | Un JSONL canónico por tabla — el estado bendecido |
| `prompts/blessing_audit.md` | Prompt LLM para auditar un blessing |
| `audits/` | Informes de resultado de auditorías LLM de blessing |

---

## 3. Inicio Rápido

```bash
# 0. Requisito previo: BD Docker local en ejecución
cd development && docker-compose up -d && cd ..

# 1. Ejecutar la suite (¡ELIMINA y reconstruye el VictaTMTK local!)
.venv/bin/python3 -m pytest tests/regression --run-regression

# 2. El `pytest` simple es seguro: sin --run-regression todo se omite,
#    por lo que los tests unitarios y CI siguen funcionando sin cambios.
.venv/bin/python3 -m pytest            # suite unitaria + regresión omitida
```

Tiempo de ejecución: ~11 segundos para el ciclo completo (reset de esquema, 170 eventos, volcado de 24 tablas, doble ejecución, 25 invariantes).

> ⚠️ La suite **destruye los datos de desarrollo local** en VictaTMTK. Si se mantiene estado
> en la BD local, rehidratar después (`development/hydrate_local_db.py` /
> `hydrate_local_small.py`).

---

## 4. El Corpus

**Procedencia.** Dos fuentes commiteadas, consumidas en este orden (el orden importa —
ver nota sobre colisión de ids en `corpus_builder.load_sources`):

1. `development/sample_payloads.json` — 18.556 eventos (filas de prod de la ventana
   Oct 2025 – Feb 2026, ids renumerados 1–18556 por el export).
   *No commiteado* (en gitignore, 60 MB) — pero los casos seleccionados sí lo están.
2. `corpus/sources/prod_topup_2026-06-11.json` — 21 filas de producción específicas
   (ids reales de prod): los eventos hijo de DrivingInsights con sus padres compartidos,
   representantes de forma de TimelineUpdate y los casos negativos.
3. `corpus/sources/prod_topup_2026-06-17.json` — 4 filas de producción para
   `UserActivityUpdate` (3 formas: UNKNOWN, STATIONARY, TRIP).

**Selección.** `corpus_builder.py` conserva el representante de id más bajo de cada par
`(tipo, forma)`, luego incluye forzosamente el `DrivingInsights` padre de cada evento hijo
seleccionado (un hijo sin su padre quedaría estacionado como huérfano y su handler nunca
se ejecutaría).

**Cobertura actual (170 casos, 168 formas):**

| Tipo | Casos | Notas |
|---|---|---|
| requestUserContext | 69 | cada forma estructural en el sample |
| UserContextUpdate | 34 | |
| DrivingInsights | 34 | 32 formas + 2 padres forzados |
| SDKStatus | 7 | |
| TimelineEvents | 6 | tipo legacy (35 filas en toda la prod) |
| TimelineUpdate | 6 | formas STATIONARY / OFF_THE_GRID / IN_TRANSPORT |
| VehicleCrash | 2 | incl. la forma `location: null` (bug real de ruta de crash) |
| UserActivityUpdate | 4 | 3 formas: UNKNOWN, STATIONARY, TRIP |
| DrivingInsightsPhoneEvents | 2 | |
| DrivingInsightsHarshEvents | 1 | |
| DrivingInsightsSpeedingEvents | 1 | |
| DrivingInsightsCallEvents | 1 | solo 2 eventos así en toda la prod |
| DebugLog / CRASH / fcm_token | 3 | **casos negativos** — deben quedar intactos |

**Gaps documentados** (`manifest.json → routed_tipos_without_coverage`):
`DrivingInsightsWrongWayDrivingEvents`, `TechnicalEvent`, `UserActivity`,
`UserMetadata` — cero ocurrencias en producción al 2026-06-11. Política: esperar
tráfico real, luego §5.4. **No escribir payloads sintéticos para ellos.**

**Los casos negativos** son eventos no enrutados reales (incluyendo una fila `CRASH` cuyo
payload es el string literal `Array` — un bug de serialización upstream que vale conservar).
Los archivos golden prueban que el ETL los deja en `is_processed = 0` sin fila de auditoría,
y un invariante lo hace cumplir para cualquier dato.

---

## 5. Procedimientos

### 5.1 Ejecutar la Suite

```bash
.venv/bin/python3 -m pytest tests/regression --run-regression
```

Agregar `-q` para salida concisa, `-k snapshot` para ejecutar solo la comparación golden.

### 5.2 Interpretar un Fallo

Un fallo de snapshot imprime un diff unificado por tabla, por ejemplo:

```
--- golden/Trip.jsonl
+++ current/Trip
-{"trip_id": 12, ..., "distance_meters": "2841.00", ...}
+{"trip_id": 12, ..., "distance_meters": null, ...}
```

Preguntar, en orden:

1. **¿Pretendía hacer este cambio?** Si no → es una regresión. El diff indica la tabla,
   la fila y el campo; corregir el código y volver a ejecutar.
2. **Si sí** → ¿es el nuevo valor *correcto* según `Documentos/MapeoSDK_BD.md`?
   Verificar las filas afectadas (el prompt de auditoría LLM §5.5 puede ayudar para diffs
   grandes), luego volver a bendecir (§5.3).
3. **¿Ruido de desplazamiento de ids?** Si se editó el corpus, los valores de identity
   se desplazan y el diff es grande pero mecánico — esperado; volver a bendecir tras
   revisar una muestra.

Un **fallo de idempotencia** significa que un segundo pass mutó datos: buscar un MERGE
que actualiza de forma no idempotente o una fila reprocesada a pesar de su flag.
Un **fallo de invariante** es independiente del corpus — leer las filas infractoras en el
mensaje de aserción; casi siempre son bugs reales.

### 5.3 Volver a Bendecir (Aceptar Nuevo Comportamiento)

```bash
.venv/bin/python3 -m pytest tests/regression --run-regression --bless
git diff tests/regression/golden/        # REVISAR ESTO — ES el cambio
git add tests/regression/golden && git commit
```

El diff de git de `golden/` es el artefacto revisable del cambio de comportamiento —
tratarlo con la misma seriedad que el diff de código que lo causó. Nunca bendecir con
un árbol de trabajo sucio mezclando cambios no relacionados.

### 5.4 Top-up del Corpus (Cuando Producción Gana Nuevo Tráfico)

Ejecutar cuando: un tipo gap empieza a aparecer en producción, se agrega un nuevo tipo de
evento al ETL, o el SDK empieza a enviar nuevas formas de payload.

```bash
# 1. Explorar qué tiene producción ahora (solo lectura; vía MCP en una sesión
#    de Claude o cualquier cliente SQL):
#    SELECT tipo, COUNT(*) FROM SentianceEventos GROUP BY tipo

# 2. Cosechar representantes reales (solo lectura, necesita .env.rds):
.venv/bin/python3 tests/regression/fetch_topup.py \
    --sample-tipo UserMetadata --candidates 12 --max-len 20000
#    ...o filas explícitas (los hijos necesitan su padre — explorar primero):
.venv/bin/python3 tests/regression/fetch_topup.py --ids 81234 81235

# 3. Si las nuevas filas son MÁS NUEVAS que snapshot_lib.CORPUS_EPOCH, primero
#    incrementar la constante de epoch (fetch_topup la rechaza de lo contrario — ver §7).

# 4. Reconstruir el corpus (el orden de fuentes importa, mantenerlo como en manifest.json):
.venv/bin/python3 tests/regression/corpus_builder.py \
    --sources development/sample_payloads.json \
              tests/regression/corpus/sources/*.json

# 5. Volver a bendecir (§5.3) y auditar SOLO los casos nuevos (§5.5).
```

### 5.5 Auditoría LLM del Blessing

Los archivos golden afirman *estabilidad*, no *corrección* — el blessing inicial (o nuevos
casos del corpus) debe auditarse una vez contra la especificación de mapeo. Abrir una sesión
de Claude Code en este repositorio y ejecutar el prompt:

```
Follow the instructions in tests/regression/prompts/blessing_audit.md.
Audit scope: <all cases | tipo=X | case ids ...>
```

La auditoría escribe `tests/regression/audits/audit_<fecha>.md` con una tabla de veredicto
por caso (PASS / FAIL / QUESTION). Un humano resuelve cada FAIL/QUESTION: el ETL está mal
(corregir código, volver a bendecir) o el golden está bien (registrar la resolución en el
archivo de auditoría). Un blessing se *confía* una vez que su auditoría no tiene ítems
abiertos.

### 5.6 Agregar un Nuevo Tipo de Evento al ETL — Checklist

- [ ] Ruteo agregado en `run()` + handler implementado (+ tests unitarios)
- [ ] Ejemplos reales de producción cosechados vía `fetch_topup.py` (§5.4)
- [ ] Snapshot cubre cualquier nueva tabla (`snapshot_lib.TABLES` — el invariante de
      cobertura falla ruidosamente si se olvida)
- [ ] Volver a bendecir + auditar los nuevos casos

---

## 6. La Suite de Invariantes

`test_invariants.py` afirma ~25 verdades estructurales que se mantienen para **cualquier**
dato ingestado, no solo el corpus: cada fila de evento hijo tiene su padre, cada fila de
dominio se remonta a un `SdkSourceEvent`, cada fila de auditoría apunta a una fila real de
la cola, no se almacenan viajes provisionales, no hay viajes `(usuario, transporte)` duplicados,
los tipos no enrutados nunca producen filas de auditoría, y la lista de tablas del snapshot
coincide exactamente con `sys.tables` (una nueva tabla objetivo del ETL no puede escapar
silenciosamente del snapshotting).

Todas las consultas de invariantes son SELECT puros. Se pueden apuntar en solo lectura contra
**producción** como verificación de calidad de datos (ej. desde una sesión de Claude vía el
servidor MCP `mssql`, o cualquier cliente SQL) — ese es su segundo trabajo, y cómo el bug
`is_processed BIT` (§8) se generaliza más allá del corpus.

Un invariante fallido marcado como `xfail` es un **bug conocido rastreado**: `strict=True`
significa que la suite da error en el momento en que el bug se corrige, forzando la limpieza
del marcador.

---

## 7. El Contrato de Determinismo

Por qué el mismo corpus siempre produce volcados idénticos byte a byte:

1. **Orden de procesamiento** — la consulta de fetch del ETL es `ORDER BY id` (corregido
   el 2026-06-11; el docstring siempre lo afirmó), la cola se carga en orden de id, y el
   pipeline es monohilo ⇒ los valores de identity en las 24 tablas son reproducibles.
2. **Reset de identity** — el esquema se elimina y recrea en cada ejecución, por lo que los
   seeds de identity siempre empiezan en 1.
3. **Enmascaramiento de timestamps en tiempo de ejecución** — cada `DATETIME` en o después
   de `snapshot_lib.CORPUS_EPOCH` (2026-06-10) se enmascara como `<run-time>`. Todos los
   eventos del corpus son anteriores al epoch, por lo que cualquier timestamp posterior solo
   puede ser ruido de `GETDATE()` / `datetime.now()`. El epoch es **absoluto, no relativo**
   — el enmascaramiento nunca cambia con el paso del tiempo del reloj. Hacer top-up con
   eventos más nuevos ⇒ incrementar el epoch ⇒ volver a bendecir (diff mecánico).
4. **GZIP descomprimido** — las columnas `VARBINARY` se almacenan como gzip (cuyo header
   embebe un timestamp ⇒ los bytes crudos no son comparables); los volcados embeben el JSON
   descomprimido, que es también lo que se quiere leer en un diff.
5. **Escalares estables** — decimales renderizados vía `str()` (escala fija por columna),
   datetimes truncados a milisegundos, trazas reducidas a su última línea (las rutas y
   números de línea cambiarían con ediciones no relacionadas).
6. **Ecos masivos excluidos** — `SentianceEventos.json` / `Errors.raw_json` duplican los
   inputs del corpus y se omiten de los volcados.

**Limitación aceptada:** insertar un caso del corpus con un id *entre* los existentes
desplaza los valores de identity downstream ⇒ un diff de re-bless mecánico grande.
Esto es deliberado — la alternativa (virtualización de ids) compra estabilidad del diff a
costa de legibilidad del volcado y complejidad del harness. Las ediciones del corpus son
raras y siempre terminan en un re-bless de todos modos.

---

## 8. Registro de Hallazgos

Problemas reales detectados por esta suite. Seguir agregando — esta sección es el historial
de la suite.

### 2026-06-11 — `is_processed` BIT colapsa el marcador de fallo (primera ejecución)

El invariante de auditoría falló en el caso del corpus 707: `is_processed = 1` sin
`SdkSourceEvent`. Causa raíz: el ETL trata `is_processed` como tri-estado
(`0` pendiente / `1` listo / `-1` fallido-u-omitido), pero la columna es `BIT` en
`development/sql/init_db.sql` **y en `development/sql/migrate_prod_stage2.sql`
(línea ~96) — por lo que el bug iría a producción al momento del go-live.** SQL Server
almacena cualquier valor distinto de cero en un BIT como 1 ⇒ cada fila fallida y cada
huérfano sin transportId se registra como *procesado exitosamente*. La forensia depende
entonces íntegramente de `SentianceEventos_Errors`, y el reprocesamiento por flag es
imposible. **Estado: CORREGIDO (2026-06-17)** — `SMALLINT` en ambos archivos SQL, marcador
`xfail` eliminado de `test_invariants.py`, diccionario de datos actualizado. Se requiere
re-bless tras recrear la BD local.

### 2026-06-11 — `process_crash_event` falla con `location: null`

El caso del corpus 707 (payload real de VehicleCrash con `"location": null`) lanzaba
`AttributeError` en `sentiance_etl.py:820` — `payload.get("location", {})` retornaba
`None` cuando la clave está presente pero es null. **Estado: CORREGIDO (2026-06-17)**
— cambiado a `payload.get("location") or {}`, mismo idioma ya usado en
`process_user_context` / `process_timeline_events`. Test unitario agregado en
`test_param_extraction.py::TestProcessCrashEventParams::test_null_location_does_not_crash`.
Golden snapshot re-bendecido: el caso 707 ahora produce una fila en `VehicleCrashEvent`.

### 2026-06-11 — Producción envía `UserActivityUpdate`, el ETL enruta `UserActivity`

112 filas de producción (Oct 2025) llevaban `tipo = 'UserActivityUpdate'`, que ninguna
entrada de enrutamiento reconocía — quedaban en `is_processed = 0` permanentemente.
`UserActivityUpdate` es el formato de payload más nuevo del SDK para el mismo concepto que
`UserActivity` pero con nombres de campo diferentes (`type` / `tripInfo.type` /
`stationaryInfo.location` en lugar de `activityType` / `tripType` / `stationaryLocation`).
**Estado: CORREGIDO (2026-06-17)** — agregado el handler `process_activity_update`,
conectado al filtro de enrutamiento y la rama de despacho. 4 casos del corpus agregados
(3 formas: UNKNOWN, STATIONARY, TRIP); golden snapshot re-bendecido. Tests unitarios en
`test_param_extraction.py::TestProcessActivityUpdateParams`.

### 2026-07-03 — `UserActivity`/`UserActivityUpdate` rompen `upsert_trip` (varchar→numeric)

Detectado corriendo el ETL contra `VictaTMTK_ETL` (sandbox de RDS con datos reales;
ver `Documentos/GuiaPruebaETL.md`). Ambos handlers de actividad creaban un viaje pasando
`sid` (un entero, el `sdk_source_event_id`) como `"id"` del transporte. `upsert_trip`
hace `MERGE ... ON canonical_transport_event_id = source.tid`; como esa columna es
`VARCHAR` y `tid` llegaba como entero, SQL Server —por precedencia de tipos— intentaba
convertir **toda la columna a numérico** y fallaba con `8114: Error converting varchar to
numeric` apenas hubiera un viaje con id string en la tabla (siempre). Cada `UserActivity` /
`UserActivityUpdate` con info de viaje terminaba en `SentianceEventos_Errors` (con rollback
de su fila de `UserActivityHistory`) en vez de generar datos. **La regresión no lo agarró**
porque sus casos `UserActivityUpdate` no ejercitan la rama de viaje contra una tabla `Trip`
ya poblada. **Estado: CORREGIDO (2026-07-03)** — un `UserActivity(Update)` no trae transport
id real de Sentiance, así que ya **no crea viaje** (el detalle del viaje llega vía
DrivingInsights / Timeline); se eliminó la llamada a `upsert_trip` de
`process_activity_history` y `process_activity_update`. Tests unitarios de guardia en
`TestProcessActivityUpdateParams::test_trip_type_does_not_create_trip` y
`TestProcessActivityHistoryParams::test_in_transport_does_not_create_trip`.
Golden re-bendecido (2026-07-03): el caso TRIP del corpus (evento 50000049) pasó de fila de
error (`SentianceEventos_Errors`, `is_processed = -1`) a fila de `UserActivityHistory`
(`is_processed = 1`, más su `SdkSourceEvent`), sin crear viaje. Diff mecánico limpio de 4
archivos golden, sin desplazamiento de ids (la nueva fila de `SdkSourceEvent` rellena el hueco
de identity que dejaba el rollback del error).

---

## 9. Límites y FAQ

**El golden codifica el comportamiento actual — incluyendo bugs actuales.** Eso es por
diseño: la suite fija *lo que es*, la auditoría (§5.5) y el registro de hallazgos establecen
*lo que debería ser*. Corregir un bug conocido produce un diff golden limpio y revisable.

**Qué NO cubre esta suite:** los cuatro tipos con gap (sin tráfico de producción aún), el
bridge Movilidad (forzado a OFF en el harness; tiene sus propios tests unitarios),
comportamiento de fallo/reintento de conexión BD (rutas de `reconnect()`), y verdadera
concurrencia (el pipeline es monohilo por diseño).

**¿Por qué los payloads del corpus están commiteados — no son datos de usuarios?** Mismo
precedente que `development/test_small_full.json` (ya commiteado): este es un repositorio
privado y el corpus es el fundamento del test. Si la política cambia, el corpus puede
regenerarse desde fuentes mantenidas fuera de git.

**¿Por qué no pytest-syrupy / librerías de snapshot?** El snapshot es un volcado de SQL
Server, no un valor Python; el dumper personalizado tiene ~150 líneas y es dueño de las
reglas de normalización, que son la parte realmente difícil.

**¿Puedo ejecutar solo los invariantes contra producción?** Sí — son SELECT puros;
ejecutarlos vía el servidor MCP `mssql` de solo lectura o cualquier cliente SQL.
No apuntar el harness de *snapshot* a producción: lo rechaza por construcción
(`harness.assert_local_only`), y mantenerlo así.
