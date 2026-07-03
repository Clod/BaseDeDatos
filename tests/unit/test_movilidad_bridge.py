"""
Unit tests for movilidad_bridge.MovilidadBridge.

These tests are pure-logic: no DB required. The src_conn and the destination
connection are MagicMocks. We assert on the SQL parameters the bridge would send.
"""

import gzip
import json
from unittest.mock import MagicMock, patch

import pytest


_FAKE_MOVILIDAD_ENV = {
    "MOVILIDAD_HOST": "localhost",
    "MOVILIDAD_PORT": "1533",
    "MOVILIDAD_DATABASE": "Movilidad",
    "MOVILIDAD_USER": "u",
    "MOVILIDAD_PASSWORD": "p",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _gzip_json(obj) -> bytes:
    return gzip.compress(json.dumps(obj).encode("utf-8"))


def _make_bridge(src_cursor_returns: dict | None = None):
    """Builds a MovilidadBridge with mocked src + dst connections.

    src_cursor_returns: maps SQL substring -> (rows | row | scalar) to return.
    """
    from movilidad_bridge import MovilidadBridge

    src_conn = MagicMock()
    src_cursor = MagicMock()
    src_conn.cursor.return_value = src_cursor

    def execute_side_effect(sql, params=None):
        src_cursor.last_sql = sql
        return src_cursor

    src_cursor.execute.side_effect = execute_side_effect

    # default: empty rows / None scalar
    src_cursor.fetchone.return_value = None
    src_cursor.fetchall.return_value = []

    bridge = MovilidadBridge(victatmtk_conn=src_conn, env=_FAKE_MOVILIDAD_ENV)

    # patch the destination connection
    dst_conn = MagicMock()
    dst_cursor = MagicMock()
    dst_cursor.fetchone.return_value = (0,)  # "no existing row"
    dst_conn.cursor.return_value = dst_cursor
    bridge._dst_conn = dst_conn

    return bridge, src_conn, src_cursor, dst_conn, dst_cursor


# ---------------------------------------------------------------------------
# Init / config
# ---------------------------------------------------------------------------


def test_init_raises_when_env_missing():
    from movilidad_bridge import MovilidadBridge

    src = MagicMock()
    with pytest.raises(ValueError, match="MOVILIDAD"):
        MovilidadBridge(victatmtk_conn=src, env={})


def test_init_builds_conn_str_correctly():
    from movilidad_bridge import MovilidadBridge

    bridge = MovilidadBridge(victatmtk_conn=MagicMock(), env=_FAKE_MOVILIDAD_ENV)
    assert "SERVER=localhost,1533" in bridge._dst_conn_str
    assert "DATABASE=Movilidad" in bridge._dst_conn_str
    assert "UID=u" in bridge._dst_conn_str


# ---------------------------------------------------------------------------
# Pure-function helpers
# ---------------------------------------------------------------------------


def test_build_polyline_encodes_waypoints():
    from movilidad_bridge import MovilidadBridge

    wp = [{"latitude": -34.6, "longitude": -58.4}, {"latitude": -34.61, "longitude": -58.41}]
    encoded = MovilidadBridge._build_polyline(wp)
    import polyline as pl
    assert pl.decode(encoded) == pytest.approx([(-34.6, -58.4), (-34.61, -58.41)], abs=1e-4)


def test_build_polyline_empty_returns_empty_string():
    from movilidad_bridge import MovilidadBridge

    assert MovilidadBridge._build_polyline([]) == ""


def test_build_polyline_skips_invalid_waypoints():
    from movilidad_bridge import MovilidadBridge

    wp = [
        {"latitude": -34.6, "longitude": -58.4},
        {"foo": "bar"},  # no lat/lon
        None,  # not a dict
        {"latitude": "notanumber", "longitude": -58.4},
        {"latitude": -34.61, "longitude": -58.41},
    ]
    encoded = MovilidadBridge._build_polyline(wp)
    import polyline as pl
    decoded = pl.decode(encoded)
    assert len(decoded) == 2


def test_extract_endpoints_returns_lat_lon_strings():
    from movilidad_bridge import MovilidadBridge

    wp = [
        {"latitude": -34.6, "longitude": -58.4},
        {"latitude": -34.7, "longitude": -58.5},
        {"latitude": -34.8, "longitude": -58.6},
    ]
    start, end = MovilidadBridge._extract_endpoints(wp)
    assert start == "-34.6,-58.4"
    assert end == "-34.8,-58.6"


def test_extract_endpoints_empty_list_returns_empty_strings():
    from movilidad_bridge import MovilidadBridge

    assert MovilidadBridge._extract_endpoints([]) == ("", "")


def test_max_speed_finds_maximum():
    from movilidad_bridge import MovilidadBridge

    wp = [
        {"speedInMps": 10.5},
        {"speedInMps": 25.0},
        {"speedInMps": 18.2},
    ]
    assert MovilidadBridge._max_speed(wp) == 25.0


def test_max_speed_handles_missing_field():
    from movilidad_bridge import MovilidadBridge

    assert MovilidadBridge._max_speed([{"latitude": 1}]) == 0.0


def test_decompress_waypoints_roundtrip():
    from movilidad_bridge import MovilidadBridge

    original = [{"latitude": 1.0, "longitude": 2.0}]
    blob = _gzip_json(original)
    assert MovilidadBridge._decompress_waypoints(blob) == original


def test_decompress_waypoints_handles_none():
    from movilidad_bridge import MovilidadBridge

    assert MovilidadBridge._decompress_waypoints(None) == []


def test_decompress_waypoints_handles_corrupt_blob():
    from movilidad_bridge import MovilidadBridge

    assert MovilidadBridge._decompress_waypoints(b"not gzip") == []


# ---------------------------------------------------------------------------
# sync_trips entry point
# ---------------------------------------------------------------------------


def test_sync_trips_empty_set_short_circuits():
    bridge, *_ = _make_bridge()
    report = bridge.sync_trips(set())
    assert report.requested == 0
    assert report.synced == 0


def test_sync_trips_handles_movilidad_unreachable():
    from movilidad_bridge import MovilidadBridge

    src = MagicMock()
    bridge = MovilidadBridge(victatmtk_conn=src, env=_FAKE_MOVILIDAD_ENV)
    bridge._dst_conn = None
    with patch("movilidad_bridge.pyodbc.connect", side_effect=Exception("network")):
        report = bridge.sync_trips({"trip-1", "trip-2"})
    assert report.requested == 2
    assert report.synced == 0
    assert report.skipped == 2
    assert report.failed == 0


def test_sync_trips_skips_when_trip_not_in_victatmtk():
    bridge, src_conn, src_cursor, dst_conn, dst_cursor = _make_bridge()
    src_cursor.fetchone.return_value = None  # Trip not found
    report = bridge.sync_trips({"trip-1"})
    assert report.synced == 0
    assert report.skipped == 1
    assert dst_conn.commit.call_count == 0


# ---------------------------------------------------------------------------
# Full _sync_one happy path
# ---------------------------------------------------------------------------


def _trip_row():
    """Returns a tuple shaped like _read_trip's SELECT result."""
    waypoints_blob = _gzip_json([
        {"latitude": -34.6, "longitude": -58.4, "speedInMps": 5.0},
        {"latitude": -34.61, "longitude": -58.41, "speedInMps": 20.0},
        {"latitude": -34.62, "longitude": -58.42, "speedInMps": 15.0},
    ])
    return (
        1,                # trip_id
        "user-abc",       # sentiance_user_id
        "trip-xyz",       # canonical_transport_event_id
        "CAR",            # transport_mode
        "2026-03-01 19:30:00.000",  # start_time
        "2026-03-01 20:00:00.000",  # end_time
        1800,             # duration_in_seconds
        12500.5,          # distance_meters
        "DRIVER",         # occupant_role
        None,             # transport_tags_json
        waypoints_blob,   # waypoints_json
        0.85,             # legal
        0.90,             # smooth
        0.75,             # attention
        0.83,             # overall
        0.80,             # focus
        0.10,             # harsh_acc
        0.05,             # harsh_brake
        0.20,             # harsh_turn
        1,                # di_id (motorised: DrivingInsightsTrip row exists)
    )


def _trip_row_non_motorised():
    """A trip with a real trajectory but NO DrivingInsights (walking / bus / bike).
    All di.* score columns and di_id come back NULL from the LEFT JOIN."""
    waypoints_blob = _gzip_json([
        {"latitude": -34.6, "longitude": -58.4, "speedInMps": 1.2},
        {"latitude": -34.601, "longitude": -58.401, "speedInMps": 1.5},
    ])
    return (
        2,                # trip_id
        "user-walk",      # sentiance_user_id
        "trip-walk",      # canonical_transport_event_id
        "WALKING",        # transport_mode
        "2026-03-02 10:00:00.000",
        "2026-03-02 10:06:00.000",
        360,              # duration_in_seconds
        405.0,            # distance_meters
        None,             # occupant_role
        None,             # transport_tags_json
        waypoints_blob,   # waypoints_json
        None, None, None, None,   # legal/smooth/attention/overall
        None, None, None, None,   # focus/harsh_acc/harsh_brake/harsh_turn
        None,             # di_id -> non-motorised
    )


def test_sync_one_happy_path_populates_all_movilidad_tables():
    """When a trip exists in VictaTMTK, sync_one should run upserts on all 7 Movilidad tables."""
    bridge, src_conn, src_cursor, dst_conn, dst_cursor = _make_bridge()

    # Stage the responses from the source DB. Each fetchone/fetchall returns
    # the next value in a queue.
    src_cursor.fetchone.side_effect = [
        _trip_row(),     # _read_trip
        (0,),            # _count_harsh_events
        None,            # _upsert_perfil_usuario: no UserContextHeader
    ]
    src_cursor.fetchall.side_effect = [
        [],  # harsh
        [],  # phone
        [],  # call
        [],  # speeding
        [],  # wrong_way
        [],  # _upsert_choque: no crashes
    ]

    report = bridge.sync_trips({"trip-xyz"})

    assert report.synced == 1
    assert report.failed == 0
    assert dst_conn.commit.called

    # Confirm MERGE statements were executed for all expected tables
    executed_sql = " ".join(
        call.args[0] for call in dst_cursor.execute.call_args_list
    )
    assert "MERGE Transporte" in executed_sql
    assert "MERGE Recorridos" in executed_sql
    assert "MERGE PuntajesPrirmariosTr" in executed_sql
    assert "MERGE PuntajesSecundariosTr" in executed_sql
    assert "MERGE Conduccion" in executed_sql
    assert "MERGE Eventos" in executed_sql
    assert "MERGE EventosSignificantes" in executed_sql


def test_sync_one_non_motorised_writes_trajectory_but_skips_puntajes():
    """Non-motorised trip (walking/bus/bike): Transporte + Recorridos are written,
    but the driving-score tables are skipped (no meaningless all-zero rows)."""
    bridge, src_conn, src_cursor, dst_conn, dst_cursor = _make_bridge()
    # No _count_harsh_events call happens (puntajes skipped), so the fetchone queue
    # is just: _read_trip, then _upsert_perfil_usuario.
    src_cursor.fetchone.side_effect = [_trip_row_non_motorised(), None]
    src_cursor.fetchall.side_effect = [[], [], [], [], [], []]

    report = bridge.sync_trips({"trip-walk"})

    assert report.synced == 1
    assert report.failed == 0

    executed_sql = " ".join(
        call.args[0] for call in dst_cursor.execute.call_args_list
    )
    # Trajectory IS projected:
    assert "MERGE Transporte" in executed_sql
    assert "MERGE Recorridos" in executed_sql
    assert "MERGE Conduccion" in executed_sql
    # Driving-score tables are NOT:
    assert "MERGE PuntajesPrirmariosTr" not in executed_sql
    assert "MERGE PuntajesSecundariosTr" not in executed_sql


# ---------------------------------------------------------------------------
# modo_transporte: traducción al vocabulario español de Movilidad
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "sdk_mode, expected",
    [
        ("CAR", "Auto"),
        ("BUS", "Colectivo"),
        ("MOTORCYCLE", "Moto"),
        ("WALKING", "Caminando"),
        ("BICYCLE", "Bicicleta"),
        ("TRAIN", "Tren"),
        ("TRAM", "Subte"),
        ("UNKNOWN", "Desconocido"),
        ("IDLE", "IDLE"),        # estado de actividad: Movilidad lo conserva en inglés
        ("RUNNING", "RUNNING"),  # idem
        ("car", "Auto"),         # case-insensitive
        (None, "Desconocido"),   # None -> UNKNOWN -> Desconocido
    ],
)
def test_modo_movilidad_translates_sdk_vocabulary(sdk_mode, expected):
    bridge, *_ = _make_bridge()
    assert bridge._modo_movilidad(sdk_mode) == expected


def test_modo_movilidad_unknown_mode_falls_back_raw_and_warns(caplog):
    import logging

    bridge, *_ = _make_bridge()
    with caplog.at_level(logging.WARNING):
        result = bridge._modo_movilidad("BOAT")
    # Un modo desconocido se deja crudo (visible) en vez de enmascararse:
    assert result == "BOAT"
    assert any("sin mapeo" in r.getMessage() for r in caplog.records)


def test_upsert_transporte_writes_spanish_mode():
    """Un viaje CAR debe escribir 'Auto' en Transporte, no 'CAR'."""
    bridge, src_conn, src_cursor, dst_conn, dst_cursor = _make_bridge()
    src_cursor.fetchone.side_effect = [_trip_row(), (0,), None]
    src_cursor.fetchall.side_effect = [[], [], [], [], [], []]

    bridge.sync_trips({"trip-xyz"})

    transporte_calls = [
        call for call in dst_cursor.execute.call_args_list
        if "MERGE Transporte" in call.args[0]
    ]
    assert transporte_calls, "no se ejecutó el MERGE de Transporte"
    params = transporte_calls[0].args[1]
    assert "Auto" in params
    assert "CAR" not in params


def test_puntajes_primarios_atencion_uses_focus_score():
    """`atencion` de Movilidad sale de focus_score, no de attention_score.
    En _trip_row: attention=0.75 (row[13]), focus=0.80 (row[15])."""
    bridge, src_conn, src_cursor, dst_conn, dst_cursor = _make_bridge()
    src_cursor.fetchone.side_effect = [_trip_row(), (0,), None]
    src_cursor.fetchall.side_effect = [[], [], [], [], [], []]

    bridge.sync_trips({"trip-xyz"})

    primarios = [
        call for call in dst_cursor.execute.call_args_list
        if "MERGE PuntajesPrirmariosTr" in call.args[0]
    ]
    assert primarios, "no se ejecutó el MERGE de PuntajesPrirmariosTr"
    params = primarios[0].args[1]
    # params = [viaje, uid, legal, suavidad, atencion, promedio, uid, viaje, ...]
    assert params[4] == 0.80, "atencion debe ser focus_score (0.80)"
    assert 0.75 not in params, "attention_score (0.75) no debe aparecer"


def test_score_absent_returns_minus_one_but_keeps_real_zero():
    """_score: None -> -1 (sin dato); 0.0 real se conserva."""
    bridge, *_ = _make_bridge()
    assert bridge._score(None) == -1.0
    assert bridge._score(0.0) == 0.0
    assert bridge._score(0.83) == 0.83


def test_primarios_absent_score_written_as_sentinel():
    """Un score ausente (None) se escribe -1, no 0. Un 0.0 real se conserva."""
    bridge, *_, dst_cursor = _make_bridge()
    trip = {"legal": None, "smooth": 0.9, "focus": None, "overall": 0.0}
    bridge._upsert_puntajes_primarios("trip-xyz", "user-abc", trip)

    params = dst_cursor.execute.call_args.args[1]
    # [viaje, uid, legal, suavidad, atencion, promedio, uid, viaje, ...]
    assert params[2] == -1.0, "legal ausente -> -1"
    assert params[3] == 0.9, "suavidad real"
    assert params[4] == -1.0, "atencion (focus) ausente -> -1"
    assert params[5] == 0.0, "promedio 0.0 real se conserva"


# ---------------------------------------------------------------------------
# ocupante: traducción al vocabulario español de Movilidad
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "sdk_role, expected",
    [
        ("DRIVER", "Conductor"),
        ("PASSENGER", "Pasajero"),
        ("UNAVAILABLE", "No disponible"),
        ("driver", "Conductor"),   # case-insensitive
        (None, None),              # None se conserva None
    ],
)
def test_ocupante_movilidad_translates_sdk_vocabulary(sdk_role, expected):
    bridge, *_ = _make_bridge()
    assert bridge._ocupante_movilidad(sdk_role) == expected


def test_ocupante_movilidad_unknown_role_falls_back_raw_and_warns(caplog):
    import logging

    bridge, *_ = _make_bridge()
    with caplog.at_level(logging.WARNING):
        result = bridge._ocupante_movilidad("PILOT")
    assert result == "PILOT"
    assert any("sin mapeo" in r.getMessage() for r in caplog.records)


def test_upsert_conduccion_writes_spanish_role():
    """Un viaje con occupant_role='DRIVER' debe escribir 'Conductor' en Conduccion."""
    bridge, src_conn, src_cursor, dst_conn, dst_cursor = _make_bridge()
    src_cursor.fetchone.side_effect = [_trip_row(), (0,), None]
    src_cursor.fetchall.side_effect = [[], [], [], [], [], []]

    bridge.sync_trips({"trip-xyz"})

    conduccion = [
        call for call in dst_cursor.execute.call_args_list
        if "MERGE Conduccion" in call.args[0]
    ]
    assert conduccion, "no se ejecutó el MERGE de Conduccion"
    params = conduccion[0].args[1]
    assert "Conductor" in params
    assert "DRIVER" not in params


def test_eventos_y_significantes_son_espejo():
    """Eventos y EventosSignificantes deben recibir los mismos arrays JSON."""
    bridge, src_conn, src_cursor, dst_conn, dst_cursor = _make_bridge()
    src_cursor.fetchone.side_effect = [_trip_row(), (0,), None]
    src_cursor.fetchall.side_effect = [[], [], [], [], [], []]

    bridge.sync_trips({"trip-xyz"})

    calls = dst_cursor.execute.call_args_list
    eventos_call = next(c for c in calls if "MERGE Eventos AS" in c.args[0])
    significantes_call = next(
        c for c in calls if "MERGE EventosSignificantes" in c.args[0]
    )

    # En cada llamada, los params de aceleracion/frenado/etc. deben coincidir.
    # Skip the first two params (viaje, usuario), and the last two `uid, viaje`
    # of the INSERT branch; compare the 8 JSON columns in each branch.
    e_params = eventos_call.args[1]
    s_params = significantes_call.args[1]

    # Both calls share the same 8 update-branch columns at indices 2..9 and
    # the same 8 insert-branch columns at indices 12..19.
    assert e_params[2:10] == s_params[2:10]
    assert e_params[12:20] == s_params[12:20]


def test_secundarios_sets_anticipacion_and_celular_fijo_sentinel():
    """Campos cloud-only (no llegan por SDK) se escriben como -1 ("sin dato"),
    igual que el Movilidad real (que tiene -1 en el 100% de las filas)."""
    bridge, src_conn, src_cursor, dst_conn, dst_cursor = _make_bridge()
    src_cursor.fetchone.side_effect = [_trip_row(), (3,), None]
    src_cursor.fetchall.side_effect = [[], [], [], [], [], []]

    bridge.sync_trips({"trip-xyz"})

    sec_call = next(
        c for c in dst_cursor.execute.call_args_list
        if "MERGE PuntajesSecundariosTr" in c.args[0]
    )
    sql = sec_call.args[0]
    assert "anticipacion = -1" in sql
    assert "celular_fijo = -1" in sql
    # eventos_fuertes debería pasarse como el conteo de harsh events (3)
    params = sec_call.args[1]
    assert 3 in params


def test_polyline_is_passed_into_recorridos_upsert():
    bridge, src_conn, src_cursor, dst_conn, dst_cursor = _make_bridge()
    src_cursor.fetchone.side_effect = [_trip_row(), (0,), None]
    src_cursor.fetchall.side_effect = [[], [], [], [], [], []]

    bridge.sync_trips({"trip-xyz"})

    rec_call = next(
        c for c in dst_cursor.execute.call_args_list
        if "MERGE Recorridos" in c.args[0]
    )
    params = rec_call.args[1]
    # polyline string is at index 3 of the UPDATE-branch params
    polyline_str = params[3]
    assert isinstance(polyline_str, str)
    assert polyline_str != ""
    import polyline as pl
    decoded = pl.decode(polyline_str)
    assert len(decoded) == 3


def test_upsert_conduccion_merges_occupant_role():
    """_upsert_conduccion debe pasar occupant_role traducido como `ocupante`."""
    bridge, *_, dst_cursor = _make_bridge()
    trip = {"occupant_role": "DRIVER"}
    bridge._upsert_conduccion("trip-xyz", "user-abc", trip)

    call = dst_cursor.execute.call_args
    sql, params = call.args[0], call.args[1]
    assert "MERGE Conduccion" in sql
    assert params == ["trip-xyz", "user-abc", "Conductor", "user-abc", "trip-xyz", "Conductor"]


def test_upsert_conduccion_accepts_none_occupant():
    """ocupante puede ser NULL (viajes sin occupant_role en el SDK)."""
    bridge, *_, dst_cursor = _make_bridge()
    bridge._upsert_conduccion("trip-xyz", "user-abc", {})

    call = dst_cursor.execute.call_args
    params = call.args[1]
    assert params[2] is None
    assert params[5] is None


def test_exception_in_sync_one_is_caught_and_reported():
    """Un fallo en un trip no debe romper la sincronización de los siguientes."""
    bridge, src_conn, src_cursor, dst_conn, dst_cursor = _make_bridge()
    src_cursor.fetchone.side_effect = Exception("DB exploded")

    report = bridge.sync_trips({"trip-xyz"})

    assert report.failed == 1
    assert report.synced == 0
    assert any("trip-xyz" in e for e in report.errors)
