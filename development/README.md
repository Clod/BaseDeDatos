# VictaTMTK — Entorno de Desarrollo Local

Este directorio contiene la infraestructura para ejecutar una instancia local de SQL Server para el desarrollo del ETL y los tests de regresión.  
**Nota:** Este setup utiliza **Azure SQL Edge**, optimizado para Apple Silicon (M1/M2/M3) y arquitecturas ARM64.

## Requisitos Previos

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) instalado y en ejecución.
- Apple Silicon (Mac) o host Linux ARM64.
- [uv](https://github.com/astral-sh/uv) o `pip` para instalar dependencias Python.

## Inicio Rápido

### 1. Levantar SQL Server

Desde este directorio, ejecutar:

```bash
docker-compose up -d
```

### 2. Inicializar el Esquema

Como MSSQL en Docker no ejecuta scripts automáticamente al iniciar, y algunas imágenes ARM64 carecen de herramientas internas, usar el bootstrapper Python provisto:

```bash
# Asegurarse de que el venv esté activo
source ../.venv/bin/activate

# Ejecutar el bootstrapper
python bootstrap_local_db.py
```

### 3. Datos de Conexión

- **Host:** `localhost`
- **Puerto:** `1433`
- **Usuario:** `sa`
- **Contraseña:** `SentianceLocal2026!`
- **Base de datos:** `VictaTMTK`

## Flujo de Desarrollo Local

1. **Hidratar:** Usar `hydrate_local_small.py` para cargar datos de prueba representativos.
2. **Desarrollar:** Actualizar `.env` para apuntar a `localhost,1433`.
3. **Probar:** Ejecutar `python sentiance_etl.py` y verificar los resultados en las tablas locales.
4. **Resetear:** Para empezar de cero, ejecutar `docker-compose down -v` para borrar todos los datos.

### Prueba desde cero (BD limpia con datos mínimos representativos)

Borrar la base de datos y recrearla vacía:

```bash
python hydrate_local_db.py --recreate-only   # Eliminar y recrear el esquema solamente
```

Cargar los dos sets de datos:

- DrivingInsights y DrivingInsights\*Event (74 registros)
- TimeLine y UserContext (9 registros)

```bash
python hydrate_local_small.py
python hydrate_local_small.py --file test_context_timeline.json
```

Ejecutar el ETL:

```bash
python ../etl/sentiance_etl.py
```

Revisar los resultados visualmente:

```bash
marimo run sentiance_inspector.py
```

## Cambios de Esquema

### Tabla Trip — trazabilidad de origen (agregado 2026-04-25)

Se agregaron dos columnas `BIGINT NULL` a `Trip` para registrar qué fila de `SdkSourceEvent` fue responsable de crear y actualizar por última vez cada viaje:

| Columna | Tipo | FK | Descripción |
|---|---|---|---|
| `creating_sdk_source_event_id` | `BIGINT NULL` | `SdkSourceEvent` | Asignado una sola vez en INSERT — el evento que descubrió el viaje por primera vez |
| `last_updated_by_sdk_source_event_id` | `BIGINT NULL` | `SdkSourceEvent` | Actualizado en cada MERGE — el último evento que refrescó los datos del viaje |

Para aplicar a una base de datos existente sin recrearla completamente:

```sql
ALTER TABLE Trip
    ADD creating_sdk_source_event_id BIGINT NULL
            REFERENCES SdkSourceEvent(sdk_source_event_id),
        last_updated_by_sdk_source_event_id BIGINT NULL
            REFERENCES SdkSourceEvent(sdk_source_event_id);
```

### Cambios de comportamiento del ETL (2026-04-25)

- **Los viajes provisionales ya no se escriben en `Trip`.**  
  `upsert_trip` ahora retorna `None` inmediatamente si `isProvisional = true`.  
  Un viaje solo se almacena cuando Sentiance lo marca como final (`isProvisional = false`).

- **Regla de validación de Trip Sync en el inspector:**  
  Para cada evento `IN_TRANSPORT` en un payload `UserContextUpdate` o `requestUserContext`:
  - `isProvisional = false` → el viaje **debe** existir en `Trip` (✅ si se encuentra, ❌ si falta)
  - `isProvisional = true` → el viaje **no debe** existir en `Trip` (✅ si está ausente, ❌ si está presente)
