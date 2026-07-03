"""
Bootstrapper de la base de prueba del ETL — VictaTMTK_ETL (sandbox en RDS)
=========================================================================

DESCRIPCIÓN:
Prepara la base `VictaTMTK_ETL` en el servidor RDS para que el ETL Stage-2
(etl/sentiance_etl.py) se pueda correr contra una copia real, del tamaño de
producción, SIN tocar la base productiva `VictaTMTK`.

`VictaTMTK_ETL` ya contiene las 14 tablas legacy y ~78k filas en
`SentianceEventos`, pero le faltan las 22 tablas de dominio Stage-2 y la columna
`is_processed` que el ETL necesita. Este script agrega exactamente eso, de forma
idempotente.

POR QUÉ UN SCRIPT DEDICADO:
`development/sql/init_db.sql` tiene hardcodeado `USE master / CREATE DATABASE
VictaTMTK / USE VictaTMTK`, así que no se puede apuntar a `VictaTMTK_ETL` tal
cual. Este script reutiliza las MISMAS definiciones de CREATE TABLE de ese
archivo pero elimina el preámbulo de base de datos, de modo que cada tabla cae
en la base a la que apunte el `.env`.

Este script NUNCA ejecuta `development/sql/migrate_prod_stage2.sql` (ese archivo
es un artefacto de producción de ejecución manual únicamente). Solo aplica los
deltas de esquema mínimos que la corrida de prueba necesita.

SEGURIDAD:
- Se niega a correr salvo que DB_NAME == 'VictaTMTK_ETL' (se puede forzar con --force).
- Nunca emite CREATE DATABASE ni ejecuta ninguna sentencia USE, así que solo
  puede afectar la base a la que se conecta.
- --reset elimina y recrea SOLO las 22 tablas Stage-2; nunca toca los datos de
  `SentianceEventos` ni las tablas legacy/bridge (Transporte, Eventos, ...).

USO:
    # Preparación inicial (crea las tablas Stage-2 + la columna is_processed):
    .venv/bin/python development/bootstrap_etl_test_db.py

    # Borrar la salida Stage-2 y re-armar la cola para probar de nuevo desde cero:
    .venv/bin/python development/bootstrap_etl_test_db.py --reset
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys

import pyodbc
from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ETL-TestDB-Bootstrap")

# Las 22 tablas de dominio Stage-2 (todo lo que crea init_db.sql EXCEPTO las dos
# tablas de landing SentianceEventos / SentianceEventos_Errors, que ya existen en
# VictaTMTK_ETL y contienen los datos fuente que queremos conservar).
STAGE2_TABLES: tuple[str, ...] = (
    "SdkSourceEvent",
    "UserMetadata",
    "Trip",
    "DrivingInsightsTrip",
    "DrivingInsightsHarshEvent",
    "DrivingInsightsPhoneEvent",
    "DrivingInsightsCallEvent",
    "DrivingInsightsSpeedingEvent",
    "DrivingInsightsWrongWayDrivingEvent",
    "UserContextHeader",
    "UserContextUpdateCriteria",
    "UserHomeHistory",
    "UserWorkHistory",
    "UserContextActiveSegmentDetail",
    "UserContextSegmentAttribute",
    "UserContextEventDetail",
    "TimelineEventHistory",
    "UserActivityHistory",
    "TechnicalEventHistory",
    "VehicleCrashEvent",
    "SdkStatusHistory",
    "UserOrganization",
)

# Batches de init_db.sql que gestionan la BASE DE DATOS en sí (no tablas). Los
# salteamos para que el esquema caiga en la base ya conectada.
_SKIP_BATCH_RE = re.compile(
    r"\bCREATE\s+DATABASE\b|\bUSE\s+(?:master|VictaTMTK)\b", re.IGNORECASE
)


def _build_conn_str() -> tuple[str, str]:
    """Arma un connection string ODBC a partir de las variables de entorno DB_*
    (las mismas que usa el ETL). Devuelve (conn_str, db_name)."""
    server = os.getenv("DB_SERVER")
    port = os.getenv("DB_PORT")
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")
    db_name = os.getenv("DB_NAME")

    missing = [
        k
        for k, v in {
            "DB_SERVER": server,
            "DB_PORT": port,
            "DB_USER": user,
            "DB_PASSWORD": password,
            "DB_NAME": db_name,
        }.items()
        if not v
    ]
    if missing:
        logger.error("Faltan variables en el .env: %s", ", ".join(missing))
        sys.exit(1)

    # La selección de driver refleja la de etl/sentiance_etl.py: respeta DB_DRIVER
    # si está seteado, si no autodetecta el driver ODBC más nuevo instalado
    # (18 → 17 → legacy).
    driver = os.getenv("DB_DRIVER")
    if not driver:
        available = pyodbc.drivers()
        for d in ("ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server", "SQL Server"):
            if d in available:
                driver = d
                break
        if not driver:
            driver = "SQL Server"

    conn_str = (
        f"DRIVER={{{driver}}};"
        f"SERVER={server},{port};"
        f"DATABASE={db_name};"
        f"UID={user};"
        f"PWD={password};"
    )
    if "ODBC Driver" in driver:
        conn_str += "Encrypt=yes;TrustServerCertificate=yes"
    return conn_str, db_name


def _load_stage2_batches() -> list[str]:
    """Lee init_db.sql y devuelve solo los batches que crean objetos Stage-2, con
    el preámbulo de CREATE DATABASE / USE ya eliminado."""
    script_path = os.path.join(os.path.dirname(__file__), "sql", "init_db.sql")
    if not os.path.exists(script_path):
        logger.error("No se encontró el esquema en: %s", script_path)
        sys.exit(1)

    with open(script_path, "r", encoding="utf-8") as f:
        sql_script = f.read()

    batches: list[str] = []
    for raw in sql_script.split("GO"):
        batch = raw.strip()
        if not batch:
            continue
        if _SKIP_BATCH_RE.search(batch):
            continue  # sentencia a nivel de base de datos — no va en una base de prueba
        batches.append(batch)
    return batches


def _run_batches(cursor: pyodbc.Cursor, batches: list[str]) -> None:
    for batch in batches:
        try:
            cursor.execute(batch)
        except Exception as exc:  # noqa: BLE001
            msg = str(exc).lower()
            if "already exists" in msg or "there is already an object" in msg:
                continue  # re-ejecución idempotente
            logger.error("Error ejecutando un batch: %s", exc)


def _ensure_is_processed(cursor: pyodbc.Cursor) -> None:
    """Agrega SentianceEventos.is_processed (SMALLINT) si falta. La tabla ya
    existe en VictaTMTK_ETL, así que el guard IF NOT EXISTS de init_db.sql la
    saltea y nunca agrega esta columna — la agregamos explícitamente acá."""
    cursor.execute(
        """
        IF NOT EXISTS (
            SELECT 1 FROM sys.columns
            WHERE object_id = OBJECT_ID('dbo.SentianceEventos') AND name = 'is_processed'
        )
            ALTER TABLE dbo.SentianceEventos
                ADD is_processed SMALLINT NOT NULL
                    CONSTRAINT DF_SentianceEventos_is_processed DEFAULT 0;
        """
    )
    # Índice filtrado que respalda el escaneo de la cola (WHERE is_processed = 0).
    cursor.execute(
        """
        IF NOT EXISTS (
            SELECT 1 FROM sys.indexes
            WHERE name = 'IX_SentianceEventos_pending'
              AND object_id = OBJECT_ID('dbo.SentianceEventos')
        )
            CREATE INDEX IX_SentianceEventos_pending
                ON dbo.SentianceEventos(id) WHERE is_processed = 0;
        """
    )


def _reset_stage2(cursor: pyodbc.Cursor) -> None:
    """Elimina las 22 tablas Stage-2 (primero las FKs) y re-arma la cola. Los
    datos fuente en SentianceEventos y las tablas legacy/bridge quedan intactos."""
    names_sql = ", ".join(f"'{t}'" for t in STAGE2_TABLES)

    # 1. Eliminar toda FK que toque una tabla Stage-2 (como padre o como referenciada).
    cursor.execute(
        f"""
        SELECT 'ALTER TABLE ' + QUOTENAME(s.name) + '.' + QUOTENAME(t.name)
               + ' DROP CONSTRAINT ' + QUOTENAME(fk.name)
        FROM sys.foreign_keys fk
        JOIN sys.tables t  ON fk.parent_object_id = t.object_id
        JOIN sys.schemas s ON t.schema_id = s.schema_id
        WHERE t.name IN ({names_sql})
           OR OBJECT_NAME(fk.referenced_object_id) IN ({names_sql});
        """
    )
    for (stmt,) in cursor.fetchall():
        cursor.execute(stmt)

    # 2. Eliminar las tablas en sí.
    for table in STAGE2_TABLES:
        cursor.execute(f"IF OBJECT_ID('dbo.{table}', 'U') IS NOT NULL DROP TABLE dbo.{table};")

    # 3. Re-armar toda la cola para que la próxima corrida del ETL reprocese todo.
    cursor.execute("UPDATE dbo.SentianceEventos SET is_processed = 0;")
    logger.info("Reset OK: tablas Stage-2 recreadas y cola re-armada (is_processed = 0).")


# Tablas para las que mostrar un conteo de filas en el resumen (salida del ETL +
# salida del bridge). El conteo solo se muestra si la tabla existe.
_COUNT_STAGE2 = ("SdkSourceEvent", "Trip", "DrivingInsightsTrip", "UserContextHeader",
                 "TimelineEventHistory", "VehicleCrashEvent")
_COUNT_BRIDGE = ("Transporte", "Recorridos", "Eventos", "PuntajesPrirmariosTr")


def _count(cursor: pyodbc.Cursor, table: str) -> int | None:
    if cursor.execute(f"SELECT OBJECT_ID('dbo.{table}', 'U')").fetchone()[0] is None:
        return None
    return cursor.execute(f"SELECT COUNT(*) FROM dbo.{table}").fetchone()[0]


def _print_summary(cursor: pyodbc.Cursor, db_name: str) -> None:
    cursor.execute(
        f"""
        SELECT
          (SELECT COUNT(*) FROM sys.tables WHERE name IN ({", ".join(f"'{t}'" for t in STAGE2_TABLES)})) AS stage2_tables,
          (SELECT COUNT(*) FROM sys.columns WHERE object_id = OBJECT_ID('dbo.SentianceEventos') AND name = 'is_processed') AS is_processed_col,
          (SELECT COUNT(*) FROM dbo.SentianceEventos WHERE is_processed = 0) AS pending_rows,
          (SELECT COUNT(*) FROM dbo.SentianceEventos) AS total_rows;
        """
    )
    stage2, has_col, pending, total = cursor.fetchone()
    logger.info("---- Resumen de %s ----", db_name)
    logger.info("Tablas Stage-2 presentes : %s / 22", stage2)
    logger.info("Columna is_processed     : %s", "sí" if has_col else "NO")
    logger.info("SentianceEventos         : %s filas (%s pendientes de procesar)", total, pending)

    logger.info("Salida del ETL (Stage-2):")
    for table in _COUNT_STAGE2:
        n = _count(cursor, table)
        logger.info("  %-22s : %s", table, "(no existe)" if n is None else n)

    logger.info("Salida del bridge Movilidad:")
    for table in _COUNT_BRIDGE:
        n = _count(cursor, table)
        logger.info("  %-22s : %s", table, "(no existe)" if n is None else n)

    if stage2 == 22 and has_col:
        logger.info("La base está lista para correr el ETL.")
    else:
        logger.warning("La base NO quedó completa — revisá los errores de arriba.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepara VictaTMTK_ETL para probar el ETL.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Borra la salida Stage-2 y re-arma la cola para probar de nuevo desde cero.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Permite correr contra un DB_NAME distinto de 'VictaTMTK_ETL'.",
    )
    args = parser.parse_args()

    # override=True: the .env file wins over any DB_* vars already exported in the
    # shell (e.g. a local-dev config in ~/.zshrc), so the guard below actually sees
    # what the .env says instead of a stale shell export.
    load_dotenv(override=True)
    conn_str, db_name = _build_conn_str()

    if db_name != "VictaTMTK_ETL" and not args.force:
        logger.error(
            "Este script es solo para la base de prueba 'VictaTMTK_ETL', pero el "
            ".env apunta a '%s'. Corregí DB_NAME en el .env (o usá --force si "
            "realmente sabés lo que hacés).",
            db_name,
        )
        sys.exit(1)

    logger.info("Conectando a %s ...", db_name)
    try:
        conn = pyodbc.connect(conn_str, autocommit=True)
    except Exception as exc:  # noqa: BLE001
        logger.error("No se pudo conectar: %s", exc)
        sys.exit(1)

    try:
        cursor = conn.cursor()

        batches = _load_stage2_batches()
        logger.info("Aplicando %s batches de esquema (idempotente)...", len(batches))
        _run_batches(cursor, batches)

        _ensure_is_processed(cursor)

        if args.reset:
            _reset_stage2(cursor)
            # Recrear las tablas recién eliminadas.
            _run_batches(cursor, batches)

        _print_summary(cursor, db_name)
    finally:
        conn.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Abortado por el usuario.")
