# Guía: Probar el ETL contra `VictaTMTK_ETL`

> **Objetivo:** correr todo el proceso contra una copia real de producción, **sin
> tocar la base de verdad (`VictaTMTK`)**.
>
> `VictaTMTK_ETL` es una **base de prueba** (una copia) en el mismo servidor de
> Amazon. Ya tiene ~78.000 registros reales, pero le faltan algunas tablas que el
> proceso necesita. Esta guía las crea, corre el proceso y verifica el resultado.
>
> **Tiempo estimado:** 15–30 minutos (según cuánto tarde en procesar los 78k registros).

---

## Diccionario rápido (para no perderse)

Antes de arrancar, tres términos que vas a ver todo el tiempo:

- **El ETL** — el programa que agarra los registros crudos que manda la app
  (guardados en la tabla `SentianceEventos`) y los transforma en tablas ordenadas
  y consultables (viajes, eventos de manejo, contexto del usuario, etc.).
- **Tablas "Stage-2"** — son justamente esas **tablas de destino donde el ETL
  guarda los datos ya procesados** (`Trip`, `DrivingInsightsTrip`,
  `UserContextHeader`, y 19 más). "Stage-2" es solo una etiqueta para
  diferenciarlas de la tabla cruda de entrada. En esta base todavía no existen:
  el primer paso de la guía las crea.
- **El bridge de Movilidad** — un paso extra al final que **copia** los viajes ya
  procesados hacia las tablas del sistema viejo Movilidad (`Transporte`,
  `Eventos`, `Recorridos`, etc.), para que Movilidad las siga viendo.

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

> ℹ️ **Sobre el `.env` y tu shell:** el ETL y el script de preparación cargan el
> `.env` con `override=True`, así que **el `.env` manda** por encima de cualquier
> variable `DB_*` / `MOVILIDAD_*` que tengas exportada en tu terminal (por ejemplo
> desde `~/.zshrc`). No hace falta hacer `unset` de nada: lo que pongas en el `.env`
> es lo que se usa. Igual, el script imprime a qué base se conecta (`Conectando a
> VictaTMTK_ETL ...`) para que lo confirmes de un vistazo.

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
# ===== Prueba del ETL contra la base de prueba VictaTMTK_ETL =====
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

> **¿Por qué el bridge apunta a `VictaTMTK_ETL`?** Porque querés probar esa copia
> hacia Movilidad dentro de la misma base. Las tablas destino (`Transporte`,
> `Eventos`, `Recorridos`, etc.) ya existen en `VictaTMTK_ETL`, así que el bridge
> escribe ahí mismo. Si algún día querés probar contra la Movilidad de verdad,
> cambiás estas 5 variables `MOVILIDAD_*`.

---

## Paso 2 — Crear el esquema de prueba

Este comando crea las 22 tablas que faltan (las tablas de destino "Stage-2") y
agrega la columna `is_processed`, que es la que marca qué registros ya se
procesaron. Podés correrlo las veces que quieras sin romper nada: si algo ya
está creado, lo saltea.

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

(Donde dice "Stage-2" son las tablas de destino que mencionamos en el diccionario;
todavía están en 0 porque el ETL no corrió aún.)

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

**3.2. Procesar todo.** Cuando la primera pasada anduvo bien, largá el proceso completo,
que repite hasta terminar con todos los registros pendientes (los ~78k):

```bash
.venv/bin/python etl/run_full_pipeline.py
```

Esto puede tardar varios minutos. La copia hacia Movilidad (el bridge) se dispara
**automáticamente** al final de cada tanda que haya procesado viajes nuevos.

---

## Paso 4 — Verificar los resultados

La forma más fácil: **volvé a correr el script de preparación** (sin `--reset`). No
cambia nada, solo te muestra el resumen actualizado con los conteos:

```bash
.venv/bin/python development/bootstrap_etl_test_db.py
```

Ahora deberías ver:

- **`0 pendientes de procesar`** (o un número muy chico) → se procesó todo.
- **Salida del ETL (las tablas de destino)** con números > 0 en `SdkSourceEvent`,
  `Trip`, `DrivingInsightsTrip`, `UserContextHeader`, etc.
- **Salida del bridge Movilidad** (la copia hacia el sistema viejo) con
  `Transporte`, `Recorridos`, `Eventos` poblados.

Si esos números crecieron respecto al Paso 2, **el proceso funcionó de punta a punta**. ✅

> **¿Quedaron filas con error?** El ETL nunca se cae por un registro malo: lo registra
> en `SentianceEventos_Errors`. Si querés ver cuántos hubo, pedile a alguien con acceso
> a la base que corra `SELECT COUNT(*) FROM VictaTMTK_ETL.dbo.SentianceEventos_Errors;`,
> o usá cualquier cliente SQL (SSMS / Azure Data Studio / DBeaver).

---

## Paso 5 — Volver a probar desde cero (opcional)

Si querés repetir la prueba desde cero (por ejemplo, después de cambiar código del
ETL), usá `--reset`. Esto **borra solo lo que generó el ETL** (las 22 tablas de
destino) y vuelve a marcar los 78k registros como pendientes. **No borra** los
registros originales de `SentianceEventos` ni los datos de las tablas del sistema
viejo:

```bash
.venv/bin/python development/bootstrap_etl_test_db.py --reset
```

Después repetí el Paso 3.

> **Nota sobre el bridge:** las tablas de Movilidad (`Transporte`, `Eventos`, ...) se
> actualizan sin duplicar (si un viaje ya está, lo actualiza en vez de repetirlo), así
> que volver a correr el ETL simplemente las vuelve a sincronizar. `--reset` no las
> vacía, porque contienen datos que conviene conservar.

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
| `Data source name not found` / error de driver ODBC | No hay un ODBC Driver de Microsoft instalado | Instalá el ODBC Driver 18 (o 17). El script y el ETL autodetectan el que haya. Si tenés uno con nombre distinto, agregá `DB_DRIVER=nombre exacto del driver` al `.env` |
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
