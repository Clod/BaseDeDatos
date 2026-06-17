# Suite de Tests — `sentiance_etl.py`

> **130 tests unitarios, sin base de datos requerida, se ejecuta en ~0,2 segundos.**

Este directorio contiene la suite de tests unitarios para `sentiance_etl.py`. Los tests están diseñados para ser rápidos, aislados y ejecutables sin ninguna base de datos ni archivo `.env`.

---

## Tabla de Contenidos

1. [Inicio Rápido](#inicio-rápido)
2. [Estructura de Directorios](#estructura-de-directorios)
3. [Cómo Funcionan los Tests (Sin BD)](#cómo-funcionan-los-tests-sin-bd)
4. [Ejecutar Tests](#ejecutar-tests)
5. [Referencia de Archivos de Tests](#referencia-de-archivos-de-tests)
6. [Referencia de Fixtures](#referencia-de-fixtures)
7. [Escribir Nuevos Tests](#escribir-nuevos-tests)
8. [Entendiendo la Cadena de Mocks](#entendiendo-la-cadena-de-mocks)
9. [Bugs Encontrados por Estos Tests](#bugs-encontrados-por-estos-tests)
10. [Tests de Regresión](#tests-de-regresión)

---

## Inicio Rápido

```bash
# Desde la raíz del proyecto
.venv/bin/python3 -m pytest tests/unit/ -v
```

Eso es todo. Sin `.env`, sin Docker, sin SQL Server.

---

## Estructura de Directorios

```
tests/
├── README.md               ← Estás aquí
├── __init__.py             ← Hace de tests/ un paquete Python
├── conftest.py             ← Fixtures compartidos (etl, mock_cursor, etl_with_cursor)
├── pytest.ini              ← Configuración de pytest (en la raíz del proyecto, no aquí)
└── unit/
    ├── __init__.py
    ├── test_format_ts.py       ← Fase 1: formateo de timestamps
    ├── test_compress.py        ← Fase 1: rondas de compresión GZIP
    ├── test_hash.py            ← Fase 1: hashing SHA-256 para deduplicación
    ├── test_param_extraction.py ← Fase 2: extracción de parámetros SQL por handler
    └── test_event_routing.py   ← Fase 2: despacho tipo → process_* + guardia de huérfanos
```

---

## Cómo Funcionan los Tests (Sin BD)

`SentianceETL.__init__()` lee variables de entorno y construye un string de conexión. Normalmente lanzaría `ValueError` si falta el archivo `.env`.

El `conftest.py` **parchea `os.getenv`** antes de instanciar la clase, para que el constructor vea valores falsos pero válidos:

```python
_FAKE_ENV = {
    "DB_SERVER": "localhost",
    "DB_PORT":   "1433",
    "DB_USER":   "sa",
    "DB_PASSWORD": "test",
    "DB_NAME":   "VictaTMTK",
}
```

La instancia se crea pero **nunca se conecta** (`connect()` nunca se llama). Todas las interacciones con la BD en los tests de Fase 2 pasan por un cursor `MagicMock`.

---

## Ejecutar Tests

### Ejecutar todo

```bash
.venv/bin/python3 -m pytest tests/unit/
```

### Con salida detallada (recomendado)

```bash
.venv/bin/python3 -m pytest tests/unit/ -v
```

### Ejecutar un único archivo de tests

```bash
.venv/bin/python3 -m pytest tests/unit/test_format_ts.py -v
```

### Ejecutar una única clase de tests

```bash
.venv/bin/python3 -m pytest tests/unit/test_format_ts.py::TestFormatTsTruncation -v
```

### Ejecutar un test específico por nombre

```bash
.venv/bin/python3 -m pytest tests/unit/test_format_ts.py::TestFormatTsTruncation::test_sub_millisecond_is_truncated_to_23_chars -v
```

### Ejecutar solo tests que coincidan con una palabra clave

```bash
# Ejecutar todos los tests con "orphan" en el nombre
.venv/bin/python3 -m pytest tests/unit/ -k "orphan" -v

# Ejecutar todos los tests con "compress" o "hash" en el nombre
.venv/bin/python3 -m pytest tests/unit/ -k "compress or hash" -v
```

### Detener en el primer fallo

```bash
.venv/bin/python3 -m pytest tests/unit/ -x
```

### Mostrar valores de variables locales en fallo (más detalle)

```bash
.venv/bin/python3 -m pytest tests/unit/ -v --tb=long
```

### Ejecutar en modo silencioso (solo la línea resumen)

```bash
.venv/bin/python3 -m pytest tests/unit/ -q
```

---

## Referencia de Archivos de Tests

### `test_format_ts.py` — Formateo de Timestamps (14 tests)

Testea `SentianceETL.format_ts()`, que convierte timestamps ISO-8601 del SDK al formato `DATETIME2(3)` de SQL Server.

**Reglas clave verificadas:**
- `"2026-04-01T14:30:00.123Z"` → `"2026-04-01 14:30:00.123"` (`T`→espacio, sin `Z`)
- La salida se **trunca estrictamente a 23 caracteres** (máximo 3 decimales)
- `None`, `""`, `0` retornan `None` (SQL `NULL`)
- La salida nunca contiene `T` ni termina con `Z`

```bash
.venv/bin/python3 -m pytest tests/unit/test_format_ts.py -v
```

---

### `test_compress.py` — Compresión GZIP (10 tests)

Testea `SentianceETL.compress_data()`, que comprime JSON con GZIP para almacenarlo en columnas `VARBINARY(MAX)` (`waypoints_json`, `transport_tags_json`, etc.).

**Reglas clave verificadas:**
- La salida es `bytes` (compatible con pyodbc)
- Descomprimir la salida y parsear el JSON es igual al objeto Python original
- Los payloads grandes son efectivamente más pequeños tras la compresión
- `None`, `[]`, `{}`, `0`, `False` retornan `None` (SQL `NULL`)

```bash
.venv/bin/python3 -m pytest tests/unit/test_compress.py -v
```

---

### `test_hash.py` — Hashing SHA-256 para Deduplicación (9 tests)

Testea `SentianceETL.get_hash()`, que genera una huella digital SHA-256 del string JSON crudo para la columna `SdkSourceEvent.payload_hash`.

**Reglas clave verificadas:**
- La misma entrada siempre produce el mismo string hexadecimal de 64 caracteres en minúsculas
- Cualquier cambio en el contenido (incluso espacios en blanco) produce un hash diferente
- La longitud de salida ≤ 64 (entra en `VARCHAR(64)`)
- Validación cruzada contra la stdlib de Python `hashlib.sha256`

```bash
.venv/bin/python3 -m pytest tests/unit/test_hash.py -v
```

---

### `test_param_extraction.py` — Extracción de Parámetros SQL (tests de parámetros)

Testea que cada handler `process_*` lee correctamente los campos del payload JSON y los pasa a `cursor.execute()` en el orden y tipo correcto.

Usa el fixture `etl_with_cursor`: una instancia ETL real conectada a un cursor `MagicMock`. Después de llamar a un handler, el test inspecciona qué parámetros SQL fueron pasados.

**Handlers cubiertos:**
| Clase | Handler |
|-------|---------|
| `TestProcessDrivingInsightsParams` | `process_driving_insights` |
| `TestProcessUserContextListenerParams` | `process_user_context` (Listener) |
| `TestProcessUserContextManualParams` | `process_user_context` (Manual) |
| `TestProcessCrashEventParams` | `process_crash_event` |
| `TestProcessSdkStatusParams` | `process_sdk_status` |
| `TestProcessMetadataParams` | `process_metadata` |
| `TestProcessTimelineEventsParams` | `process_timeline_events` |
| `TestProcessActivityUpdateParams` | `process_activity_update` |

```bash
.venv/bin/python3 -m pytest tests/unit/test_param_extraction.py -v
```

---

### `test_event_routing.py` — Despacho de Eventos + Guardia de Huérfanos (21 tests)

Testea la lógica de ruteo del método `run()` y su protección de eventos hijo huérfanos.

**Tests de ruteo (parametrizados, 15 tipos de eventos):**
Cada valor `tipo` soportado se verifica para llamar al método `process_*` correcto.

**Tests de guardia de huérfanos (4 tests):**
Cuando un evento hijo (`DrivingInsightsHarshEvents`, etc.) llega antes que su registro padre `DrivingInsights`, debe ser **omitido y dejado con `is_processed=0`** para reintento. Si no tiene `transportId`, debe marcarse `is_processed=-1`.

**Tests del valor de retorno de `run()` (3 tests):**
- Retorna `False` cuando no hay filas
- Retorna `True` cuando al menos un registro fue procesado
- Retorna `False` cuando todos los registros del batch son hijos huérfanos (previene bucles infinitos en `run_full_pipeline.py`)

```bash
.venv/bin/python3 -m pytest tests/unit/test_event_routing.py -v
```

---

## Referencia de Fixtures

Todos los fixtures están definidos en `tests/conftest.py` y están disponibles para todos los archivos de tests automáticamente (pytest descubre `conftest.py` automáticamente).

### `etl`

Una instancia `SentianceETL` con `os.getenv` parcheado. La instancia **no está conectada** a ninguna base de datos. Usar para tests de Fase 1 de funciones puras (`format_ts`, `compress_data`, `get_hash`).

```python
def test_algo(etl):
    result = etl.format_ts("2026-04-01T10:00:00Z")
    assert result == "2026-04-01 10:00:00"
```

### `mock_cursor`

Un `MagicMock` que imita un cursor `pyodbc`. Su `fetchone()` retorna `(999,)` por defecto (simulando `@@IDENTITY` o un resultado `SELECT`). Se puede sobreescribir en tests individuales:

```python
def test_algo(mock_cursor):
    mock_cursor.fetchone.return_value = (42,)
    # ... usar mock_cursor según necesidad
```

### `etl_with_cursor`

Una instancia `etl` cuyo atributo `cursor` está asignado a un `mock_cursor`. Usar para tests de Fase 2 de métodos `process_*`:

```python
def test_algo(etl_with_cursor):
    etl_with_cursor.process_sdk_status(sid=1, uid="u1", payload={...})
    params = etl_with_cursor.cursor.execute.call_args_list[0].args[1]
    assert params[2] == "STARTED"
```

---

## Escribir Nuevos Tests

### Agregar un test para un nuevo método `process_*`

1. Agregar una nueva clase a `test_param_extraction.py`
2. Usar el fixture `etl_with_cursor`
3. Construir un dict de payload mínimo y realista
4. Llamar al método
5. Inspeccionar `_get_call_params(etl_with_cursor.cursor, <índice_llamada>)`

```python
class TestProcessMiNuevoHandler:

    def test_mi_campo_extraido(self, etl_with_cursor):
        payload = {"miCampo": "valor_esperado", ...}
        etl_with_cursor.process_mi_nuevo_handler(sid=1, uid="u1", payload=payload)
        params = _get_call_params(etl_with_cursor.cursor, 0)
        assert params[3] == "valor_esperado"
```

### Agregar un test para un nuevo `tipo` en la tabla de ruteo

Agregar una nueva entrada a la lista `@pytest.mark.parametrize` en `TestEventRouting.test_tipo_dispatches_to_correct_handler`:

```python
("MiNuevoTipoDeEvento", "process_mi_nuevo_handler"),
```

Y agregar el mock al fixture `routed_etl`:

```python
etl.process_mi_nuevo_handler = MagicMock()
```

### Cómo encontrar qué llamada `execute()` inspeccionar

Cada método `process_*` hace múltiples llamadas a `cursor.execute()` (una por INSERT/SELECT). Usar este patrón para encontrar la correcta:

```python
all_calls = _execute_calls(etl_with_cursor.cursor)
# Imprimir todas las sentencias SQL y sus params para depuración:
for i, (sql, params) in enumerate(all_calls):
    print(f"Llamada {i}: {sql[:60]}...")
    print(f"  params: {params}")
```

---

## Entendiendo la Cadena de Mocks

> ⚠️ Esto es lo más importante que hay que entender al escribir tests de ruteo.

El ETL usa **llamadas encadenadas**:

```python
# Así consulta el ETL:
result = self.cursor.execute("SELECT ...", params).fetchone()
```

En `MagicMock`, `cursor_mock.execute(...).fetchone()` **no es lo mismo** que `cursor_mock.fetchone()`. La forma encadenada llama a `fetchone` sobre el **valor de retorno de `execute()`**, que es un objeto Mock separado:

```python
# ❌ INCORRECTO — configura el mock equivocado:
cursor_mock.fetchone.return_value = None

# ✅ CORRECTO — configura la llamada encadenada:
cursor_mock.execute.return_value.fetchone.return_value = None
```

Esta distinción importa principalmente para:
- La verificación del padre huérfano: `cursor.execute("SELECT 1 FROM DrivingInsightsTrip...").fetchone()`
- La búsqueda de `@@IDENTITY`: `cursor.execute("SELECT @@IDENTITY").fetchone()[0]`
- La búsqueda de `trip_id`: `cursor.execute("SELECT trip_id FROM Trip...").fetchone()`

---

## Bugs Encontrados por Estos Tests

La suite de tests descubrió **un bug real de producción** en `sentiance_etl.py`:

### `AttributeError` con `venue: null` en payloads de eventos

**Ubicación:** `process_user_context()` y `process_timeline_events()`  
**Causa raíz:** `e.get("venue", {})` retorna `None` (no `{}`) cuando el payload JSON contiene `"venue": null`. El valor por defecto `{}` solo se usa cuando la **clave está ausente**, no cuando la clave está presente con valor `null`.

```python
# ❌ Antes (falla cuando venue: null en JSON):
e.get("venue", {}).get("significance")

# ✅ Después (maneja tanto clave ausente como valor null):
(e.get("venue") or {}).get("significance")
```

Este crash ocurriría silenciosamente en producción (capturado por el manejador de errores, registrado en `SentianceEventos_Errors`) para cualquier evento estacionario o de timeline donde el SDK envíe un `null` explícito para el campo venue.

---

## Tests de Regresión

La suite unitaria cubre **únicamente la lógica de transformación sin estado**. El comportamiento de extremo a extremo está cubierto por la **suite de regresión de golden-snapshot** en `tests/regression/`: un corpus congelado de eventos reales de producción se ejecuta a través del ETL real contra el SQL Server Docker local, y el estado resultante de las 24 tablas se compara byte a byte contra archivos golden bendecidos. También incluye idempotencia, ordenamiento de huérfanos y ~25 invariantes estructurales.

```bash
# Requiere Docker DB en ejecución; ELIMINA la base de datos local VictaTMTK
.venv/bin/python3 -m pytest tests/regression --run-regression
```

Filosofía, procedimientos (blessing, top-up del corpus, auditoría LLM) y el registro de hallazgos están en **`tests/regression/README.md`**.
