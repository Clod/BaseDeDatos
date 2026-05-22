"""
MOVILIDAD BRIDGE (TEMPORARY)
============================

Proyecta los datos consolidados en VictaTMTK hacia las tablas heredadas de
Movilidad. Reemplaza el viejo pipeline de CSV-offloads de la nube de Sentiance.

DISEÑO:
- Aislado en un único archivo, removible borrando este archivo + ~10 líneas
  en sentiance_etl.py (ver "REEMPLAZO FUTURO").
- Lee de VictaTMTK (fuente de verdad), escribe a Movilidad vía MERGE idempotente.
- Tolera caídas de Movilidad sin romper el ETL principal (log warning + sigue).

REEMPLAZO FUTURO:
Cuando Operaciones implemente un proceso propio que lea VictaTMTK directamente:
1. Borrar este archivo.
2. Quitar de sentiance_etl.py: el import try/except, la inicialización del
   bridge en __init__, el set self._dirty_transport_ids en run(), y la
   llamada a sync_trips al final del batch.

VARIABLES DE ENTORNO REQUERIDAS:
- ENABLE_MOVILIDAD_BRIDGE      ("true" para activar; cualquier otro = off)
- MOVILIDAD_HOST               (ej. AROCLNDSQL-DEV.ikeasistencia.com.ar)
- MOVILIDAD_PORT               (ej. 1533)
- MOVILIDAD_DATABASE           (ej. Movilidad)
- MOVILIDAD_USER, MOVILIDAD_PASSWORD

USO:
    bridge = MovilidadBridge(victatmtk_conn=etl.conn)
    bridge.sync_trips({"transport-id-1", "transport-id-2"})
"""

from __future__ import annotations

import gzip
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Optional

import pyodbc

try:
    import polyline as polyline_lib
except ImportError as exc:
    raise ImportError(
        "MovilidadBridge requires the 'polyline' package. "
        "Install with: pip install polyline"
    ) from exc

logger = logging.getLogger("movilidad_bridge")


@dataclass(frozen=True)
class SyncReport:
    """Resultado de una invocación a sync_trips."""

    requested: int
    synced: int
    skipped: int
    failed: int
    errors: tuple[str, ...] = field(default_factory=tuple)


class MovilidadBridge:
    """Proyecta datos consolidados en VictaTMTK hacia las tablas de Movilidad.

    Tablas pobladas: Transporte, Recorridos, PuntajesPrirmariosTr (sic),
    PuntajesSecundariosTr, Eventos, EventosSignificantes, Conduccion,
    PerfilDeUsuario, ChoqueDeVehiculo.

    Limitaciones documentadas (cloud-only en Sentiance, no disponibles vía SDK):
        - `anticipacion` -> 0
        - `celular_fijo` -> 0 / "[]"
        - `pantalla`     -> "[]"
    """

    REQUIRED_ENV: tuple[str, ...] = (
        "MOVILIDAD_HOST",
        "MOVILIDAD_PORT",
        "MOVILIDAD_DATABASE",
        "MOVILIDAD_USER",
        "MOVILIDAD_PASSWORD",
    )

    def __init__(
        self,
        victatmtk_conn: pyodbc.Connection,
        env: Optional[dict[str, str]] = None,
    ) -> None:
        self.src_conn = victatmtk_conn
        env = env if env is not None else dict(os.environ)
        missing = [k for k in self.REQUIRED_ENV if not env.get(k)]
        if missing:
            raise ValueError(
                f"MovilidadBridge: faltan variables de entorno: {missing}"
            )
        self._dst_conn_str = self._build_conn_str(env)
        self._dst_conn: Optional[pyodbc.Connection] = None

    @staticmethod
    def _build_conn_str(env: dict[str, str]) -> str:
        return (
            "DRIVER={ODBC Driver 18 for SQL Server};"
            f"SERVER={env['MOVILIDAD_HOST']},{env['MOVILIDAD_PORT']};"
            f"DATABASE={env['MOVILIDAD_DATABASE']};"
            f"UID={env['MOVILIDAD_USER']};"
            f"PWD={env['MOVILIDAD_PASSWORD']};"
            "Encrypt=yes;TrustServerCertificate=yes"
        )

    def _ensure_dst_conn(self) -> bool:
        if self._dst_conn is not None:
            return True
        try:
            logger.debug("MovilidadBridge: conectando a Movilidad...")
            self._dst_conn = pyodbc.connect(self._dst_conn_str)
            logger.info("MovilidadBridge: conexión a Movilidad establecida")
            return True
        except Exception as exc:
            logger.warning(
                "MovilidadBridge: Movilidad inalcanzable, sincronización omitida: %s",
                exc,
            )
            self._dst_conn = None
            return False

    def close(self) -> None:
        if self._dst_conn is not None:
            try:
                self._dst_conn.close()
            except Exception:
                pass
            self._dst_conn = None

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def sync_trips(self, transport_ids: set[str]) -> SyncReport:
        if not transport_ids:
            return SyncReport(0, 0, 0, 0)
        if not self._ensure_dst_conn():
            return SyncReport(len(transport_ids), 0, len(transport_ids), 0)

        synced = skipped = failed = 0
        errors: list[str] = []
        for tid in transport_ids:
            try:
                if self._sync_one(tid):
                    synced += 1
                else:
                    skipped += 1
            except Exception as exc:
                failed += 1
                errors.append(f"{tid}: {exc}")
                logger.exception(
                    "MovilidadBridge: fallo sincronizando transport_id=%s", tid
                )
                try:
                    if self._dst_conn is not None:
                        self._dst_conn.rollback()
                except Exception:
                    pass

        logger.info(
            "MovilidadBridge: solicitados=%d sincronizados=%d omitidos=%d fallidos=%d",
            len(transport_ids), synced, skipped, failed,
        )
        return SyncReport(
            requested=len(transport_ids),
            synced=synced,
            skipped=skipped,
            failed=failed,
            errors=tuple(errors),
        )

    # ------------------------------------------------------------------
    # Lecturas desde VictaTMTK
    # ------------------------------------------------------------------

    def _read_trip(self, transport_id: str) -> Optional[dict[str, Any]]:
        cur = self.src_conn.cursor()
        cur.execute(
            """
            SELECT t.trip_id, t.sentiance_user_id, t.canonical_transport_event_id,
                   t.transport_mode, t.start_time, t.end_time, t.duration_in_seconds,
                   t.distance_meters, t.occupant_role,
                   t.transport_tags_json, t.waypoints_json,
                   di.legal_score, di.smooth_score, di.attention_score, di.overall_score,
                   di.focus_score, di.harsh_acceleration_score, di.harsh_braking_score,
                   di.harsh_turning_score
            FROM Trip t
            LEFT JOIN DrivingInsightsTrip di
              ON di.canonical_transport_event_id = t.canonical_transport_event_id
             AND di.sentiance_user_id = t.sentiance_user_id
            WHERE t.canonical_transport_event_id = ?
            """,
            (transport_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return {
            "trip_id": row[0],
            "uid": row[1],
            "viaje": row[2],
            "transport_mode": row[3],
            "start_time": row[4],
            "end_time": row[5],
            "duration_s": row[6],
            "distance_m": row[7],
            "occupant_role": row[8],
            "transport_tags_gzip": row[9],
            "waypoints_gzip": row[10],
            "legal": row[11], "smooth": row[12],
            "attention": row[13], "overall": row[14],
            "focus": row[15], "harsh_acc": row[16],
            "harsh_brake": row[17], "harsh_turn": row[18],
        }

    def _read_child_events(
        self,
        transport_id: str,
        uid: str,
        table: str,
        columns: list[str],
    ) -> list[dict[str, Any]]:
        cur = self.src_conn.cursor()
        cols_sql = ", ".join(f"e.{c}" for c in columns)
        cur.execute(
            f"""
            SELECT {cols_sql}
            FROM {table} e
            JOIN DrivingInsightsTrip di
              ON di.driving_insights_trip_id = e.driving_insights_trip_id
            WHERE di.canonical_transport_event_id = ?
              AND di.sentiance_user_id = ?
            ORDER BY e.start_time
            """,
            (transport_id, uid),
        )
        out: list[dict[str, Any]] = []
        for row in cur.fetchall():
            record = {col: self._coerce_cell(cell) for col, cell in zip(columns, row)}
            out.append(record)
        return out

    @staticmethod
    def _coerce_cell(cell: Any) -> Any:
        if cell is None:
            return None
        if isinstance(cell, (bytes, bytearray)):
            try:
                return json.loads(gzip.decompress(cell).decode("utf-8"))
            except Exception:
                return None
        if hasattr(cell, "isoformat"):
            return cell.isoformat()
        if hasattr(cell, "__float__") and not isinstance(cell, (int, float, bool, str)):
            try:
                return float(cell)
            except Exception:
                return str(cell)
        return cell

    # ------------------------------------------------------------------
    # Helpers de transformación
    # ------------------------------------------------------------------

    @staticmethod
    def _decompress_waypoints(blob: Optional[bytes]) -> list[Any]:
        if not blob:
            return []
        try:
            data = json.loads(gzip.decompress(blob).decode("utf-8"))
            return data if isinstance(data, list) else []
        except Exception as exc:
            logger.warning("MovilidadBridge: no pude descomprimir waypoints: %s", exc)
            return []

    @staticmethod
    def _build_polyline(waypoints: list[Any]) -> str:
        coords: list[tuple[float, float]] = []
        for wp in waypoints:
            if not isinstance(wp, dict):
                continue
            lat = wp.get("latitude", wp.get("lat"))
            lon = wp.get("longitude", wp.get("lon"))
            if lat is None or lon is None:
                continue
            try:
                coords.append((float(lat), float(lon)))
            except (TypeError, ValueError):
                continue
        return polyline_lib.encode(coords) if coords else ""

    @staticmethod
    def _extract_endpoints(waypoints: list[Any]) -> tuple[str, str]:
        def fmt(wp: Any) -> str:
            if not isinstance(wp, dict):
                return ""
            lat = wp.get("latitude", wp.get("lat"))
            lon = wp.get("longitude", wp.get("lon"))
            if lat is None or lon is None:
                return ""
            return f"{lat},{lon}"

        if not waypoints:
            return "", ""
        return fmt(waypoints[0]), fmt(waypoints[-1])

    @staticmethod
    def _max_speed(waypoints: list[Any]) -> float:
        speeds: list[float] = []
        for wp in waypoints:
            if not isinstance(wp, dict):
                continue
            s = wp.get("speedInMps", wp.get("speed"))
            if s is None:
                continue
            try:
                speeds.append(float(s))
            except (TypeError, ValueError):
                continue
        return max(speeds) if speeds else 0.0

    @staticmethod
    def _decode_tags(blob: Optional[bytes]) -> Optional[str]:
        if not blob:
            return None
        try:
            return gzip.decompress(blob).decode("utf-8")
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Sync de un trip completo
    # ------------------------------------------------------------------

    def _sync_one(self, transport_id: str) -> bool:
        logger.debug("MovilidadBridge: sincronizando transport_id=%s", transport_id)
        trip = self._read_trip(transport_id)
        if not trip:
            logger.warning(
                "MovilidadBridge: trip %s no encontrado en VictaTMTK; omitiendo",
                transport_id,
            )
            return False

        uid = trip["uid"]
        waypoints = self._decompress_waypoints(trip["waypoints_gzip"])
        polyline_str = self._build_polyline(waypoints)
        loc_start, loc_end = self._extract_endpoints(waypoints)
        max_speed = self._max_speed(waypoints)

        self._upsert_transporte(transport_id, uid, trip, max_speed)
        self._upsert_recorridos(
            transport_id, uid, trip, polyline_str, waypoints,
            loc_start, loc_end, max_speed,
        )
        self._upsert_puntajes_primarios(transport_id, uid, trip)
        harsh_count = self._count_harsh_events(transport_id, uid)
        self._upsert_puntajes_secundarios(transport_id, uid, trip, harsh_count)
        self._upsert_conduccion(transport_id, uid, trip)
        eventos = self._build_eventos_payload(transport_id, uid)
        self._upsert_eventos(transport_id, uid, eventos)
        self._upsert_eventos_significantes(transport_id, uid, eventos)
        self._upsert_choque(uid)
        self._upsert_perfil_usuario(uid)

        assert self._dst_conn is not None
        self._dst_conn.commit()
        logger.info(
            "MovilidadBridge: transport_id=%s sincronizado OK (uid=%s)", transport_id, uid
        )
        return True

    # ------------------------------------------------------------------
    # Upserts en Movilidad
    # ------------------------------------------------------------------

    def _exec_dst(self, sql: str, params: list[Any]) -> None:
        assert self._dst_conn is not None
        self._dst_conn.cursor().execute(sql, params)

    def _upsert_transporte(
        self, viaje: str, uid: str, trip: dict[str, Any], max_speed: float
    ) -> None:
        sql = """
        MERGE Transporte AS target
        USING (SELECT ? AS viaje, ? AS usuario) AS src
        ON target.viaje = src.viaje AND target.usuario = src.usuario
        WHEN MATCHED THEN UPDATE SET
            modo_transporte = ?, comienzo = ?, fin = ?, duracion = ?,
            metadata = ?, velocidad_maxima = ?
        WHEN NOT MATCHED THEN INSERT
            (usuario, viaje, modo_transporte, comienzo, fin, duracion,
             metadata, velocidad_maxima)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """
        metadata = self._decode_tags(trip["transport_tags_gzip"])
        modo = trip["transport_mode"] or "UNKNOWN"
        duracion = int(trip["duration_s"] or 0)
        params = [
            viaje, uid,
            modo, trip["start_time"], trip["end_time"], duracion,
            metadata, max_speed,
            uid, viaje, modo, trip["start_time"], trip["end_time"], duracion,
            metadata, max_speed,
        ]
        self._exec_dst(sql, params)

    def _upsert_recorridos(
        self,
        viaje: str,
        uid: str,
        trip: dict[str, Any],
        polyline_str: str,
        waypoints: list[Any],
        loc_start: str,
        loc_end: str,
        max_speed: float,
    ) -> None:
        sql = """
        MERGE Recorridos AS target
        USING (SELECT ? AS viaje, ? AS usuario) AS src
        ON target.viaje = src.viaje AND target.usuario = src.usuario
        WHEN MATCHED THEN UPDATE SET
            distancia_m = ?, polyline = ?, puntos_recorrido = ?,
            ubicacion_inicio = ?, ubicacion_fin = ?, maxima_velocidad = ?
        WHEN NOT MATCHED THEN INSERT
            (usuario, viaje, distancia_m, polyline, puntos_recorrido,
             ubicacion_inicio, ubicacion_fin, maxima_velocidad)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """
        distancia = float(trip["distance_m"] or 0)
        puntos = json.dumps(waypoints) if waypoints else "[]"
        # polyline es NOT NULL en Recorridos — si no hay waypoints, igual va string vacío.
        params = [
            viaje, uid,
            distancia, polyline_str, puntos, loc_start, loc_end, max_speed,
            uid, viaje, distancia, polyline_str, puntos,
            loc_start, loc_end, max_speed,
        ]
        self._exec_dst(sql, params)

    def _upsert_puntajes_primarios(
        self, viaje: str, uid: str, trip: dict[str, Any]
    ) -> None:
        sql = """
        MERGE PuntajesPrirmariosTr AS target
        USING (SELECT ? AS viaje, ? AS usuario) AS src
        ON target.viaje = src.viaje AND target.usuario = src.usuario
        WHEN MATCHED THEN UPDATE SET
            legal = ?, suavidad = ?, atencion = ?, promedio = ?
        WHEN NOT MATCHED THEN INSERT
            (usuario, viaje, legal, suavidad, atencion, promedio)
            VALUES (?, ?, ?, ?, ?, ?);
        """
        legal = float(trip["legal"] or 0)
        suave = float(trip["smooth"] or 0)
        aten = float(trip["attention"] or 0)
        prom = float(trip["overall"] or 0)
        params = [
            viaje, uid,
            legal, suave, aten, prom,
            uid, viaje, legal, suave, aten, prom,
        ]
        self._exec_dst(sql, params)

    def _upsert_puntajes_secundarios(
        self, viaje: str, uid: str, trip: dict[str, Any], harsh_count: int
    ) -> None:
        sql = """
        MERGE PuntajesSecundariosTr AS target
        USING (SELECT ? AS viaje, ? AS usuario) AS src
        ON target.viaje = src.viaje AND target.usuario = src.usuario
        WHEN MATCHED THEN UPDATE SET
            concentracion = ?, aceleracion_fuerte = ?, frenado_fuerte = ?,
            curvas_fuertes = ?, anticipacion = 0, celular_fijo = 0,
            eventos_fuertes = ?
        WHEN NOT MATCHED THEN INSERT
            (usuario, viaje, concentracion, aceleracion_fuerte, frenado_fuerte,
             curvas_fuertes, anticipacion, celular_fijo, eventos_fuertes)
            VALUES (?, ?, ?, ?, ?, ?, 0, 0, ?);
        """
        focus = float(trip["focus"] or 0)
        h_acc = float(trip["harsh_acc"] or 0)
        h_br = float(trip["harsh_brake"] or 0)
        h_tu = float(trip["harsh_turn"] or 0)
        params = [
            viaje, uid,
            focus, h_acc, h_br, h_tu, harsh_count,
            uid, viaje, focus, h_acc, h_br, h_tu, harsh_count,
        ]
        self._exec_dst(sql, params)

    def _count_harsh_events(self, viaje: str, uid: str) -> int:
        cur = self.src_conn.cursor()
        cur.execute(
            """
            SELECT COUNT(*) FROM DrivingInsightsHarshEvent e
            JOIN DrivingInsightsTrip di
              ON di.driving_insights_trip_id = e.driving_insights_trip_id
            WHERE di.canonical_transport_event_id = ?
              AND di.sentiance_user_id = ?
            """,
            (viaje, uid),
        )
        row = cur.fetchone()
        return int(row[0]) if row and row[0] is not None else 0

    def _build_eventos_payload(self, viaje: str, uid: str) -> dict[str, str]:
        harsh = self._read_child_events(
            viaje, uid, "DrivingInsightsHarshEvent",
            ["start_time", "end_time", "magnitude", "confidence",
             "harsh_type", "waypoints_json"],
        )
        phone = self._read_child_events(
            viaje, uid, "DrivingInsightsPhoneEvent",
            ["start_time", "end_time", "call_state", "waypoints_json"],
        )
        call = self._read_child_events(
            viaje, uid, "DrivingInsightsCallEvent",
            ["start_time", "end_time", "min_traveled_speed_mps",
             "max_traveled_speed_mps", "hands_free_state", "waypoints_json"],
        )
        speeding = self._read_child_events(
            viaje, uid, "DrivingInsightsSpeedingEvent",
            ["start_time", "end_time", "waypoints_json"],
        )
        wrong_way = self._read_child_events(
            viaje, uid, "DrivingInsightsWrongWayDrivingEvent",
            ["start_time", "end_time", "waypoints_json"],
        )

        def by_type(t: str) -> list[dict[str, Any]]:
            return [h for h in harsh if h.get("harsh_type") == t]

        return {
            "aceleracion": json.dumps(by_type("ACCELERATION")),
            "frenado": json.dumps(by_type("BRAKING")),
            "curvas": json.dumps(by_type("TURN")),
            "uso_telefono": json.dumps(phone),
            "llamados": json.dumps(call),
            "exceso_de_velocidad": json.dumps(speeding + wrong_way),
            "celular_fijo": "[]",
            "pantalla": "[]",
        }

    def _upsert_eventos(
        self, viaje: str, uid: str, ev: dict[str, str]
    ) -> None:
        sql = """
        MERGE Eventos AS target
        USING (SELECT ? AS viaje, ? AS usuario) AS src
        ON target.viaje = src.viaje AND target.usuario = src.usuario
        WHEN MATCHED THEN UPDATE SET
            aceleracion = ?, uso_telefono = ?, curvas = ?, celular_fijo = ?,
            frenado = ?, exceso_de_velocidad = ?, llamados = ?, pantalla = ?
        WHEN NOT MATCHED THEN INSERT
            (usuario, viaje, aceleracion, uso_telefono, curvas, celular_fijo,
             frenado, exceso_de_velocidad, llamados, pantalla)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        params = [
            viaje, uid,
            ev["aceleracion"], ev["uso_telefono"], ev["curvas"], ev["celular_fijo"],
            ev["frenado"], ev["exceso_de_velocidad"], ev["llamados"], ev["pantalla"],
            uid, viaje,
            ev["aceleracion"], ev["uso_telefono"], ev["curvas"], ev["celular_fijo"],
            ev["frenado"], ev["exceso_de_velocidad"], ev["llamados"], ev["pantalla"],
        ]
        self._exec_dst(sql, params)

    def _upsert_eventos_significantes(
        self, viaje: str, uid: str, ev: dict[str, str]
    ) -> None:
        # En EventosSignificantes la columna se llama `exceso_velocidad` (sin _de_).
        sql = """
        MERGE EventosSignificantes AS target
        USING (SELECT ? AS viaje, ? AS usuario) AS src
        ON target.viaje = src.viaje AND target.usuario = src.usuario
        WHEN MATCHED THEN UPDATE SET
            aceleracion = ?, uso_telefono = ?, curvas = ?, celular_fijo = ?,
            frenado = ?, exceso_velocidad = ?, llamados = ?, pantalla = ?
        WHEN NOT MATCHED THEN INSERT
            (usuario, viaje, aceleracion, uso_telefono, curvas, celular_fijo,
             frenado, exceso_velocidad, llamados, pantalla)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        params = [
            viaje, uid,
            ev["aceleracion"], ev["uso_telefono"], ev["curvas"], ev["celular_fijo"],
            ev["frenado"], ev["exceso_de_velocidad"], ev["llamados"], ev["pantalla"],
            uid, viaje,
            ev["aceleracion"], ev["uso_telefono"], ev["curvas"], ev["celular_fijo"],
            ev["frenado"], ev["exceso_de_velocidad"], ev["llamados"], ev["pantalla"],
        ]
        self._exec_dst(sql, params)

    def _upsert_conduccion(
        self, viaje: str, uid: str, trip: dict[str, Any]
    ) -> None:
        sql = """
        MERGE Conduccion AS target
        USING (SELECT ? AS viaje, ? AS usuario) AS src
        ON target.viaje = src.viaje AND target.usuario = src.usuario
        WHEN MATCHED THEN UPDATE SET ocupante = ?
        WHEN NOT MATCHED THEN INSERT (usuario, viaje, ocupante) VALUES (?, ?, ?);
        """
        ocupante = trip.get("occupant_role")
        self._exec_dst(sql, [viaje, uid, ocupante, uid, viaje, ocupante])

    def _upsert_choque(self, uid: str) -> None:
        cur = self.src_conn.cursor()
        cur.execute(
            """
            SELECT crash_time_epoch, latitude, longitude, accuracy, altitude,
                   magnitude, speed_at_impact, delta_v, confidence,
                   severity, detector_mode
            FROM VehicleCrashEvent
            WHERE sentiance_user_id = ?
            """,
            (uid,),
        )
        rows = cur.fetchall()
        if not rows:
            return
        assert self._dst_conn is not None
        for row in rows:
            payload = {
                "crash_time_epoch": row[0],
                "latitude": float(row[1]) if row[1] is not None else None,
                "longitude": float(row[2]) if row[2] is not None else None,
                "accuracy": float(row[3]) if row[3] is not None else None,
                "altitude": float(row[4]) if row[4] is not None else None,
                "magnitude": float(row[5]) if row[5] is not None else None,
                "speed_at_impact": float(row[6]) if row[6] is not None else None,
                "delta_v": float(row[7]) if row[7] is not None else None,
                "confidence": float(row[8]) if row[8] is not None else None,
                "severity": row[9],
                "detector_mode": row[10],
            }
            existing = self._dst_conn.cursor().execute(
                """
                SELECT COUNT(*) FROM ChoqueDeVehiculo
                WHERE usuario = ?
                  AND JSON_VALUE(json, '$.crash_time_epoch') = ?
                """,
                (uid, str(payload["crash_time_epoch"])),
            ).fetchone()
            if existing and existing[0] == 0:
                self._dst_conn.cursor().execute(
                    "INSERT INTO ChoqueDeVehiculo (usuario, Registro, json) "
                    "VALUES (?, GETDATE(), ?)",
                    (uid, json.dumps(payload)),
                )

    def _upsert_perfil_usuario(self, uid: str) -> None:
        cur = self.src_conn.cursor()
        cur.execute(
            """
            SELECT TOP 1 user_context_payload_id, semantic_time,
                   last_known_latitude, last_known_longitude
            FROM UserContextHeader
            WHERE sentiance_user_id = ?
            ORDER BY user_context_payload_id DESC
            """,
            (uid,),
        )
        row = cur.fetchone()
        if not row:
            return
        payload = {
            "user_context_payload_id": int(row[0]) if row[0] is not None else None,
            "semantic_time": row[1],
            "last_known_latitude": float(row[2]) if row[2] is not None else None,
            "last_known_longitude": float(row[3]) if row[3] is not None else None,
        }
        assert self._dst_conn is not None
        exists = self._dst_conn.cursor().execute(
            "SELECT COUNT(*) FROM PerfilDeUsuario WHERE usuario = ?", (uid,)
        ).fetchone()
        if exists and exists[0] > 0:
            self._dst_conn.cursor().execute(
                "UPDATE PerfilDeUsuario SET json = ?, Registro = GETDATE() "
                "WHERE usuario = ?",
                (json.dumps(payload), uid),
            )
        else:
            self._dst_conn.cursor().execute(
                "INSERT INTO PerfilDeUsuario (Registro, usuario, json) "
                "VALUES (GETDATE(), ?, ?)",
                (uid, json.dumps(payload)),
            )
