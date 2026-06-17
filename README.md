# BaseDeDatos — Pipeline ETL del SDK de Sentiance

Pipeline ETL que procesa los payloads webhook del SDK de Sentiance enviados por la aplicación móvil vía REST y los carga en un modelo relacional SQL Server (VictaTMTK). Maneja eventos de conducción, eventos de línea de tiempo, contexto de usuario, detección de choques y estado del SDK para el producto VictaTMTK.

---

## Arquitectura

```
Aplicación Móvil (SDK Sentiance)
        │  REST (payloads webhook)
        ▼
SentianceEventos        ← cola de payloads crudos (SQL Server)
        │
        ▼
etl/sentiance_etl.py    ← motor ETL principal
  ├─ DrivingInsights     → Trip, DrivingInsightsTrip
  ├─ Harsh/Phone/Call/Speeding/WrongWay events → tablas de eventos hijo
  ├─ UserContext         → UserContextHeader + 6 tablas hijo
  ├─ TimelineEvents      → TimelineEventHistory
  ├─ VehicleCrash        → VehicleCrashEvent
  └─ SDKStatus           → SdkStatusHistory
        │
        │  opcional (ENABLE_MOVILIDAD_BRIDGE=true)
        ▼
etl/movilidad_bridge.py → esquema heredado Movilidad
```

---

## Estructura del Proyecto

```
etl/                        Código ETL de producción
  sentiance_etl.py          Motor principal — lee SentianceEventos, escribe tablas de dominio
  run_full_pipeline.py      Orquestador — itera hasta vaciar la cola
  movilidad_bridge.py       Bridge temporal hacia el esquema heredado Movilidad

scripts/
  sync_movilidad.py         Utilidad de backfill — sincroniza viajes existentes a Movilidad

development/                Herramientas de desarrollo local
  docker-compose.yml        SQL Server local (Azure SQL Edge, compatible con ARM64)
  hydrate_local_db.py       Carga el dataset completo de payloads en la BD local
  hydrate_local_small.py    Carga un dataset curado pequeño (rápido, recomendado)
  sentiance_inspector.py    Dashboard visual Marimo para validación del ETL
  run_inspector_batch.py    Validador batch sin interfaz (compatible con CI)
  sql/init_db.sql           DDL del esquema VictaTMTK
  sql/init_movilidad.sql    DDL del esquema Movilidad local

tests/                      Suite de tests unitarios (no requiere base de datos)
Documentos/                 Documentación de referencia y diccionarios de datos
  DiccionarioDatos.md       Diccionario de datos completo de VictaTMTK
  analisis_mapeo_movilidad.md  Análisis de mapeo de campos SDK ↔ Movilidad
  schemas.json              Referencia del esquema Movilidad (exportación de producción)
```

---

## Configuración

### Requisitos previos

- Python 3.10+
- `brew install unixodbc` (macOS)
- [Microsoft ODBC Driver 18 para SQL Server](https://learn.microsoft.com/es-es/sql/connect/odbc/download-odbc-driver-for-sql-server)
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (para la BD local)
- `uv` (recomendado) o `pip`

### Instalar dependencias Python

```bash
uv pip install --python .venv/bin/python -r requirements.txt
```

### Configurar `.env`

```
DB_SERVER=<host>
DB_PORT=<puerto>
DB_USER=<usuario>
DB_PASSWORD=<contraseña>
DB_NAME=VictaTMTK
```

Copiar `.env.rds` como punto de partida para producción, o usar las credenciales locales indicadas más abajo para desarrollo.

---

## Ejecutar el ETL

### Batch único (hasta 1000 registros)

Procesa un batch de `SentianceEventos` y termina. Útil para pruebas.

```bash
python etl/sentiance_etl.py
```

### Pipeline continuo (corre hasta vaciar la cola)

Itera hasta procesar todos los registros con `is_processed = 0`. Usar en producción o para cargas históricas masivas.

```bash
python etl/run_full_pipeline.py
```

---

## Flujo de Desarrollo Local

### 1. Iniciar SQL Server local

```bash
cd development && docker-compose up -d
```

Conexión local: `localhost:1433 / sa / SentianceLocal2026!`

### 2. Cargar datos de prueba

Hay dos scripts de hidratación según la necesidad:

#### `hydrate_local_small.py` — dataset curado pequeño (recomendado para desarrollo)

Carga un dataset de prueba representativo (`test_small_full.json`, ~1,3 MB). Siempre crea primero los esquemas VictaTMTK y Movilidad. Usar para desarrollo ETL diario y tests unitarios.

```bash
cd development

# Cargar dataset de prueba estándar (DrivingInsights + Timeline + UserContext)
python hydrate_local_small.py

# Cargar un dataset alternativo (ej. solo eventos Timeline/UserContext)
python hydrate_local_small.py --file test_context_timeline.json
```

#### `hydrate_local_db.py` — cargador del dataset completo

Carga el dataset completo `sample_payloads.json.gz` (~900 MB descomprimido, ~52 MB comprimido). Usar cuando se necesitan volúmenes de datos de escala productiva o probar casos borde no cubiertos por el dataset pequeño.

```bash
cd development

# Limpiar datos existentes y recargar (por defecto) — limpia VictaTMTK y Movilidad
python hydrate_local_db.py

# Eliminar y recrear ambos esquemas, luego cargar datos (reset completo)
python hydrate_local_db.py --recreate

# Eliminar y recrear ambos esquemas sin cargar datos (pizarrón en blanco)
python hydrate_local_db.py --recreate-only

# Agregar datos sin limpiar los existentes
python hydrate_local_db.py --no-clear

# Cargar solo los primeros N registros
python hydrate_local_db.py --limit 500

# Cargar desde un archivo específico
python hydrate_local_db.py --file mis_payloads.json.gz
```

### 3. Configurar `.env` para desarrollo local

Crear o actualizar `.env` en la raíz del proyecto. Para un setup local completo (VictaTMTK + bridge Movilidad):

```
# VictaTMTK — instancia Docker local
DB_SERVER=localhost
DB_PORT=1433
DB_USER=sa
DB_PASSWORD=SentianceLocal2026!
DB_NAME=VictaTMTK

# Bridge Movilidad — misma instancia Docker, base de datos diferente
ENABLE_MOVILIDAD_BRIDGE=true
MOVILIDAD_HOST=localhost
MOVILIDAD_PORT=1433
MOVILIDAD_DATABASE=Movilidad
MOVILIDAD_USER=sa
MOVILIDAD_PASSWORD=SentianceLocal2026!
```

> **Importante:** si `ENABLE_MOVILIDAD_BRIDGE` no está presente o no es `true`, el bridge se
> deshabilita silenciosamente. Movilidad quedará vacía incluso tras una ejecución ETL exitosa.

### 4. Ejecutar el ETL localmente

```bash
python etl/sentiance_etl.py
```

### 5. Validar resultados con el inspector

```bash
# Dashboard visual interactivo
.venv/bin/marimo run development/sentiance_inspector.py

# Validador batch sin interfaz (muestra pass/fail por registro)
python development/run_inspector_batch.py
```

---

## Bridge Movilidad (Temporal)

Proyecta los viajes procesados de VictaTMTK hacia el esquema heredado Movilidad al final de cada batch ETL. Controlado por `ENABLE_MOVILIDAD_BRIDGE`; diseñado para ser eliminado una vez que Operaciones implemente su propio pipeline.

El bridge está completamente autocontenido en `etl/movilidad_bridge.py`. Si el host de Movilidad no es alcanzable, el bridge registra una advertencia y el ETL continúa normalmente — nunca interrumpe el pipeline principal.

### Tablas que se populan

| Tabla Movilidad | Fuente en VictaTMTK |
|-----------------|---------------------|
| `Transporte` | `Trip` |
| `Recorridos` | `Trip.waypoints_json` |
| `PuntajesPrirmariosTr` | `DrivingInsightsTrip` |
| `PuntajesSecundariosTr` | `DrivingInsightsTrip` + `DrivingInsightsHarshEvent` |
| `Conduccion` | `Trip.occupant_role` |
| `Eventos` | Todas las tablas de eventos hijo |
| `EventosSignificantes` | Espejo de `Eventos` (solo eventos significativos) |
| `PerfilDeUsuario` | `UserContextHeader` (último snapshot por usuario) |
| `ChoqueDeVehiculo` | `VehicleCrashEvent` |

### ¿Cuándo se ejecuta el bridge?

El bridge se dispara **automáticamente** al final de cada batch ETL, pero solo cuando el batch procesó al menos un nuevo evento `DrivingInsights`. Esto significa:

- Si se ejecuta el ETL con una cola nueva → el bridge sincroniza esos viajes automáticamente.
- Si se ejecuta el ETL sobre una cola **ya procesada** → `_dirty_transport_ids` está vacío → el bridge no se llama → Movilidad queda vacía.
- Si `ENABLE_MOVILIDAD_BRIDGE` no es `true` en `.env` → el bridge está desactivado por completo.

### `.env` para producción (AWS RDS → Movilidad on-prem)

```
ENABLE_MOVILIDAD_BRIDGE=true
MOVILIDAD_HOST=AROCLNDSQL-DEV.ikeasistencia.com.ar
MOVILIDAD_PORT=1533
MOVILIDAD_DATABASE=Movilidad
MOVILIDAD_USER=<usuario>
MOVILIDAD_PASSWORD=<contraseña>
```

### `.env` para desarrollo local (Docker)

```
ENABLE_MOVILIDAD_BRIDGE=true
MOVILIDAD_HOST=localhost
MOVILIDAD_PORT=1433
MOVILIDAD_DATABASE=Movilidad
MOVILIDAD_USER=sa
MOVILIDAD_PASSWORD=SentianceLocal2026!
```

---

## Procesamiento Completo Incluyendo Movilidad

### Flujo local completo desde cero

```bash
# 1. Iniciar Docker
cd development && docker-compose up -d && cd ..

# 2. Crear esquemas y cargar datos de prueba
python development/hydrate_local_small.py

# 3. Asegurarse de que .env tenga la configuración de VictaTMTK y Movilidad (ver arriba)

# 4. Ejecutar el ETL — el bridge se dispara automáticamente al final del batch
python etl/sentiance_etl.py

# 5. Verificar que Movilidad fue populada
```

Tras el paso 4, estas tablas de Movilidad deberían tener datos:
`Transporte`, `Recorridos`, `PuntajesPrirmariosTr`, `PuntajesSecundariosTr`,
`Conduccion`, `Eventos`, `EventosSignificantes`.

### Verificar datos en Movilidad (vía MCP o cualquier cliente SQL)

```sql
SELECT 'Transporte'          AS tabla, COUNT(*) AS filas FROM Movilidad.dbo.Transporte          UNION ALL
SELECT 'Recorridos',                   COUNT(*)          FROM Movilidad.dbo.Recorridos           UNION ALL
SELECT 'PuntajesPrirmariosTr',         COUNT(*)          FROM Movilidad.dbo.PuntajesPrirmariosTr UNION ALL
SELECT 'PuntajesSecundariosTr',        COUNT(*)          FROM Movilidad.dbo.PuntajesSecundariosTr UNION ALL
SELECT 'Conduccion',                   COUNT(*)          FROM Movilidad.dbo.Conduccion           UNION ALL
SELECT 'Eventos',                      COUNT(*)          FROM Movilidad.dbo.Eventos              UNION ALL
SELECT 'EventosSignificantes',         COUNT(*)          FROM Movilidad.dbo.EventosSignificantes;
```

---

## Reprocesamiento y Backfill

Usar `scripts/sync_movilidad.py` en cualquiera de estas situaciones:

- El bridge fue agregado o habilitado después de que el ETL ya procesó registros históricos.
- Movilidad fue vaciada y necesita reconstruirse desde los datos de VictaTMTK.
- Se desea re-sincronizar usuarios específicos o un rango de fechas tras un cambio de esquema.
- El bridge falló a mitad de ejecución y dejó Movilidad parcialmente populada.

El script lee directamente desde la tabla `Trip` en VictaTMTK — no importa si los eventos en `SentianceEventos` están procesados o no.

### Uso

```bash
# Sincronizar todos los viajes de VictaTMTK a Movilidad
python scripts/sync_movilidad.py

# Sincronizar solo los viajes de un usuario específico
python scripts/sync_movilidad.py --uid <sentiance_user_id>

# Sincronizar solo viajes que iniciaron a partir de una fecha
python scripts/sync_movilidad.py --since 2026-05-01

# Combinar filtros
python scripts/sync_movilidad.py --uid abc123 --since 2026-04-01

# Vista previa de lo que se sincronizaría sin escribir nada
python scripts/sync_movilidad.py --dry-run

# Procesar en bloques más pequeños (por defecto: 50 viajes por batch)
python scripts/sync_movilidad.py --batch-size 20
```

### Reset completo de Movilidad + resincronización

Si se necesita reconstruir Movilidad desde cero (ej. tras un cambio de esquema):

```bash
# 1. Limpiar y recrear solo el esquema Movilidad (deja VictaTMTK intacto)
python development/hydrate_local_db.py --recreate-only

# 2. Resincronizar todos los viajes desde VictaTMTK
python scripts/sync_movilidad.py
```

O para un reset completo de ambas bases de datos:

```bash
# 1. Eliminar y recrear ambos esquemas, recargar todos los datos de prueba
python development/hydrate_local_db.py --recreate

# 2. Ejecutar ETL — el bridge se dispara automáticamente
python etl/run_full_pipeline.py
```

### ¿Por qué Movilidad sigue vacía después de ejecutar el ETL?

**Verificación 1: ¿Está habilitado el bridge?**

El `.env` debe contener `ENABLE_MOVILIDAD_BRIDGE=true`. Si esa variable está ausente o tiene cualquier otro valor, el bridge se omite silenciosamente. El log del ETL mostrará:
```
MovilidadBridge: desactivado (ENABLE_MOVILIDAD_BRIDGE != true)
```

**Verificación 2: ¿Los eventos ya estaban procesados?**

El bridge solo se ejecuta cuando el batch ETL actual procesó nuevos eventos `DrivingInsights`.
Si todos los eventos en `SentianceEventos` tienen `is_processed = 1`, el ETL termina temprano (sin trabajo pendiente) y el bridge nunca se llama. Verificar con:

```sql
SELECT tipo, COUNT(*) AS total, SUM(CAST(is_processed AS INT)) AS procesados
FROM VictaTMTK.dbo.SentianceEventos
GROUP BY tipo
ORDER BY tipo;
```

Si las filas de `DrivingInsights` están todas procesadas, usar `sync_movilidad.py` para el backfill.

**Verificación 3: ¿Es correcta la conexión a Movilidad?**

Si el bridge está habilitado pero el host es incorrecto o el contenedor Docker no está corriendo, el bridge registra una advertencia y continúa silenciosamente. Ejecutar `scripts/sync_movilidad.py` manualmente — levantará un error claro si la conexión falla.

Ver `Documentos/analisis_mapeo_movilidad.md` § 10 para instrucciones de eliminación del bridge.

---

## Tests

```bash
.venv/bin/pytest tests/ -q
```

Todos los tests son puramente unitarios (no requieren base de datos). Cubren ruteo ETL, formateo de timestamps, compresión GZIP, hashing SHA-256, extracción de parámetros SQL y el bridge Movilidad.

---

## Lectura Adicional

- `CLAUDE.md` — configuración de servidores MCP, referencia completa del esquema VictaTMTK, contexto para el asistente de IA
- `README_ENG.md` — versión en inglés de este documento
- `Documentos/DiccionarioDatos.md` — diccionario de datos completo para las 23 tablas
- `Documentos/analisis_mapeo_movilidad.md` — mapeo de campos SDK Sentiance ↔ Movilidad
- `development/README.md` — configuración de Docker y detalles del SQL Server local
