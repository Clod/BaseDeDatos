# Guía: Probar el ETL contra `VictaTMTK_ETL`

> **Objetivo:** correr el ETL completo (incluido el bridge de Movilidad) contra una
> copia real de producción, **sin tocar la base productiva `VictaTMTK`**.
>
> `VictaTMTK_ETL` es una base sandbox en el mismo servidor RDS. Ya tiene ~78.000
> registros reales en `SentianceEventos`, pero le faltan las tablas nuevas que el
> ETL necesita. Esta guía las crea, corre el ETL y verifica el resultado.
>
> **Tiempo estimado:** 15–30 minutos (según cuánto tarde en procesar los 78k registros).

---

## Antes de empezar (requisitos)

Necesitás, en la máquina donde vas a correr esto:

1. **El repositorio clonado** y estar parado en su carpeta raíz:
   ```bash
   cd /ruta/a/BaseDeDatos
   ```
2. **El entorno Python (`.venv`) ya armado.** Si no lo tenés:
   ```bash
   uv pip install --python .venv/bin/python -r requirements.txt
   ```
3. **El driver ODBC 18 de Microsoft** instalado (en Mac: `brew install unixodbc` + el driver de Microsoft). Si el ETL ya te funcionó alguna vez, ya lo tenés.
4. **El archivo `.env.rds`** en la raíz del proyecto, con la contraseña real de la base RDS. Debería verse así (la contraseña ya está puesta):
   ```
   DB_SERVER=ltkbase003.cjo9vciowl0y.us-east-1.rds.amazonaws.com
   DB_PORT=9433
   DB_USER=ClaudioVicta
   DB_PASSWORD=********
   DB_NAME=VictaTMTK
   ```

> ⚠️ **Regla de oro:** en toda esta guía trabajamos con `DB_NAME=VictaTMTK_ETL`.
> Nunca `VictaTMTK` a secas (esa es la base productiva). El script de preparación
> se niega a correr si apuntás a la base equivocada, así que es difícil equivocarse.

---

## Paso 1 — Preparar el archivo `.env`

El ETL lee sus credenciales del archivo `.env` (sin extensión) en la raíz del proyecto.
Vamos a hacer un `.env` que apunte a la base de prueba.

**1.1.** Guardá una copia de tu `.env` actual (si tenés uno de desarrollo local), para
poder volver atrás después:

```bash
cp .env .env.backup 2>/dev/null || echo "No había .env previo, seguimos."
```

**1.2.** Creá el nuevo `.env` para la prueba. Copiá y pegá este bloque **entero** en la
terminal (tomará automáticamente la contraseña desde tu `.env.rds`):

```bash
PWD_RDS=$(grep '^DB_PASSWORD=' .env.rds | cut -d= -f2-)

cat > .env <<EOF
# ===== Prueba del ETL contra la base sandbox VictaTMTK_ETL =====
DB_SERVER=ltkbase003.cjo9vciowl0y.us-east-1.rds.amazonaws.com
DB_PORT=9433
DB_USER=ClaudioVicta
DB_PASSWORD=${PWD_RDS}
DB_NAME=VictaTMTK_ETL

# ===== Bridge de Movilidad — apunta a la MISMA base VictaTMTK_ETL =====
ENABLE_MOVILIDAD_BRIDGE=true
MOVILIDAD_HOST=ltkbase003.cjo9vciowl0y.us-east-1.rds.amazonaws.com
MOVILIDAD_PORT=9433
MOVILIDAD_DATABASE=VictaTMTK_ETL
MOVILIDAD_USER=ClaudioVicta
MOVILIDAD_PASSWORD=${PWD_RDS}
EOF

echo "Listo. .env creado apuntando a VictaTMTK_ETL."
```

> **¿Por qué el bridge apunta a `VictaTMTK_ETL`?** Porque querés probar el bridge
> dentro de la misma base. Las tablas destino del bridge (`Transporte`, `Eventos`,
> `Recorridos`, etc.) ya existen en `VictaTMTK_ETL`, así que el bridge escribe ahí
> mismo. Si algún día querés probar contra la Movilidad real, cambiás estas 5
> variables `MOVILIDAD_*`.

---

## Paso 2 — Crear el esquema de prueba

Este comando crea las 22 tablas que faltan y agrega la columna `is_processed`.
Es **idempotente**: podés correrlo las veces que quieras sin romper nada.

```bash
.venv/bin/python development/bootstrap_etl_test_db.py
```

Al terminar vas a ver un resumen como este:

```
---- Resumen de VictaTMTK_ETL ----
Tablas Stage-2 presentes : 22 / 22
Columna is_processed     : sí
SentianceEventos         : 77845 filas (77845 pendientes de procesar)
Salida del ETL (Stage-2):
  SdkSourceEvent         : 0
  Trip                   : 0
  ...
La base está lista para correr el ETL.
```

Si dice **`22 / 22`** y **`is_processed: sí`**, quedó todo listo. Si no, revisá los
mensajes de error de más arriba (casi siempre es la conexión o la contraseña).

---

## Paso 3 — Correr el ETL

**3.1. Primera pasada de prueba (un solo lote).** Procesa hasta 1000 registros y termina.
Sirve para confirmar que todo funciona antes de largar los 78k:

```bash
.venv/bin/python etl/sentiance_etl.py
```

Mirá que termine **sin errores**. Si hay filas problemáticas, el ETL las manda a la
tabla `SentianceEventos_Errors` y sigue — no se cae.

**3.2. Procesar toda la cola.** Cuando la primera pasada anduvo bien, largá el pipeline
completo, que itera hasta vaciar la cola (los ~78k registros):

```bash
.venv/bin/python etl/run_full_pipeline.py
```

Esto puede tardar varios minutos. El bridge de Movilidad se dispara **automáticamente**
al final de cada lote que haya procesado viajes nuevos.

---

## Paso 4 — Verificar los resultados

La forma más fácil: **volvé a correr el script de preparación** (sin `--reset`). No
cambia nada, solo te muestra el resumen actualizado con los conteos:

```bash
.venv/bin/python development/bootstrap_etl_test_db.py
```

Ahora deberías ver:

- **`0 pendientes de procesar`** (o un número muy chico) → la cola se procesó.
- **Salida del ETL (Stage-2)** con números > 0 en `SdkSourceEvent`, `Trip`,
  `DrivingInsightsTrip`, `UserContextHeader`, etc.
- **Salida del bridge Movilidad** con `Transporte`, `Recorridos`, `Eventos` poblados.

Si esos números crecieron respecto al Paso 2, **el ETL y el bridge funcionaron**. ✅

> **¿Quedaron filas con error?** El ETL nunca se cae por un registro malo: lo registra
> en `SentianceEventos_Errors`. Si querés ver cuántos hubo, pedile a alguien con acceso
> a la base que corra `SELECT COUNT(*) FROM VictaTMTK_ETL.dbo.SentianceEventos_Errors;`,
> o usá cualquier cliente SQL (SSMS / Azure Data Studio / DBeaver).

---

## Paso 5 — Volver a probar desde cero (opcional)

Si querés repetir la prueba limpia (por ejemplo, después de cambiar código del ETL),
usá `--reset`. Esto **borra solo la salida del ETL** (las 22 tablas Stage-2) y vuelve a
marcar los 78k registros como pendientes. **No borra** los registros originales de
`SentianceEventos` ni los datos de las tablas legacy:

```bash
.venv/bin/python development/bootstrap_etl_test_db.py --reset
```

Después repetí el Paso 3.

> **Nota sobre el bridge:** las tablas del bridge (`Transporte`, `Eventos`, ...) se
> actualizan con MERGE idempotente, así que volver a correr el ETL simplemente las
> re-sincroniza. `--reset` no las vacía (contienen datos espejo que conviene conservar).

---

## Paso 6 — Restaurar tu `.env` de siempre

Cuando terminaste de probar, volvé a tu configuración anterior:

```bash
mv .env.backup .env 2>/dev/null && echo "Restaurado tu .env original." || echo "No había backup; borrá el .env de prueba si querés."
```

---

## Problemas comunes

| Síntoma | Causa probable | Solución |
|---|---|---|
| `Este script es solo para la base de prueba 'VictaTMTK_ETL'...` | El `.env` tiene `DB_NAME` mal | Revisá el Paso 1.2; tiene que decir `DB_NAME=VictaTMTK_ETL` |
| `No se pudo conectar` / timeout | Contraseña mal, VPN caída, o el RDS no es alcanzable desde tu red | Verificá que puedas conectarte a la base con un cliente SQL; revisá `.env.rds` |
| `Data source name not found` / error de driver ODBC | Falta el ODBC Driver 18 de Microsoft | Instalá el driver (ver Requisitos) |
| `MovilidadBridge requires the 'polyline' package` | Falta la dependencia `polyline` | `uv pip install --python .venv/bin/python polyline` |
| El resumen muestra `is_processed: NO` | El `ALTER TABLE` no se aplicó | Volvé a correr el script del Paso 2; si sigue, revisá permisos del usuario en la base |
| Muchas filas en `SentianceEventos_Errors` | Payloads que el ETL no supo mapear | Es esperable que haya algunos; si son muchísimos, avisá a quien mantiene el ETL |

---

## Resumen ultra-corto (para el que ya lo hizo una vez)

```bash
cd /ruta/a/BaseDeDatos
cp .env .env.backup 2>/dev/null
PWD_RDS=$(grep '^DB_PASSWORD=' .env.rds | cut -d= -f2-)
# ...crear .env de prueba (ver Paso 1.2)...

.venv/bin/python development/bootstrap_etl_test_db.py      # crear esquema
.venv/bin/python etl/sentiance_etl.py                     # probar 1 lote
.venv/bin/python etl/run_full_pipeline.py                 # procesar todo
.venv/bin/python development/bootstrap_etl_test_db.py      # verificar resultados

mv .env.backup .env                                       # restaurar
```
