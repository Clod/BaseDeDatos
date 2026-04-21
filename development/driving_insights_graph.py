# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "marimo",
#     "pandas",
#     "pyodbc",
#     "python-dotenv",
#     "pyvis",
# ]
# ///

"""
Driving Insights Tree Graph (Marimo Notebook)
=============================================

PURPOSE:
Interactive tree visualization of a selected DrivingInsights record,
showing all related rows across domain tables.  Nodes are draggable;
zoom and pan work out of the box.

TREE STRUCTURE:
  SentianceEventos
  └── SdkSourceEvent
      └── DrivingInsightsTrip
          ├── Trip  (via canonical_transport_event_id)
          ├── DrivingInsightsHarshEvent         (0..N)
          ├── DrivingInsightsPhoneEvent         (0..N)
          ├── DrivingInsightsCallEvent          (0..N)
          ├── DrivingInsightsSpeedingEvent      (0..N)
          └── DrivingInsightsWrongWayDrivingEvent (0..N)

USAGE:
    marimo run development/driving_insights_graph.py
    marimo edit development/driving_insights_graph.py

AUTHOR: Claudio Grasso / AI Assistant
DATE: April 2026
"""

import marimo

__generated_with = "0.23.1"
app = marimo.App(width="full")


@app.cell
def load_dependencies():
    import os
    import pyodbc
    import pandas as pd
    import marimo as mo
    from dotenv import dotenv_values

    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    env_local = dotenv_values(os.path.join(root_dir, ".env"))
    env_rds   = dotenv_values(os.path.join(root_dir, ".env.rds"))

    envs_dict = {"Local (Docker)": env_local}
    if env_rds and env_rds.get("DB_SERVER"):
        envs_dict["AWS RDS (Production)"] = env_rds

    def get_conn_str(env_name):
        env = envs_dict.get(env_name)
        return (
            f"DRIVER={{ODBC Driver 18 for SQL Server}};"
            f"SERVER={env.get('DB_SERVER')},{env.get('DB_PORT')};"
            f"DATABASE={env.get('DB_NAME')};"
            f"UID={env.get('DB_USER')};"
            f"PWD={env.get('DB_PASSWORD')};"
            f"Encrypt=yes;TrustServerCertificate=yes"
        )

    return pyodbc, pd, mo, envs_dict, get_conn_str


@app.cell
def create_ui(mo, envs_dict):
    env_selector = mo.ui.dropdown(
        options=list(envs_dict.keys()),
        value="Local (Docker)",
        label="Environment: ",
    )
    limit_selector = mo.ui.number(start=10, stop=500, value=50, step=10, label="Records: ")

    header = mo.md(f"""
    # 🔍 Driving Insights — Interactive Tree Graph
    *Select a processed DrivingInsights record. Nodes are draggable; scroll to zoom.*

    {env_selector} | {limit_selector}
    ---
    """)
    return env_selector, limit_selector, header


@app.cell
def load_records(env_selector, limit_selector, get_conn_str, pyodbc, pd, mo):
    import warnings as _w

    _query = f"""
        SELECT TOP {limit_selector.value}
            se.id,
            se.sentianceid,
            se.created_at,
            ssk.sdk_source_event_id,
            dit.driving_insights_trip_id,
            CAST(dit.overall_score AS FLOAT)    AS overall_score,
            CAST(dit.distance_meters AS FLOAT)  AS distance_meters
        FROM SentianceEventos se
        LEFT JOIN SdkSourceEvent ssk
               ON ssk.sentiance_eventos_id = se.id
        LEFT JOIN DrivingInsightsTrip dit
               ON dit.sdk_source_event_id = ssk.sdk_source_event_id
        WHERE se.tipo = 'DrivingInsights'
          AND se.is_processed = 1
        ORDER BY se.id DESC
    """
    try:
        _conn = pyodbc.connect(get_conn_str(env_selector.value))
        with _w.catch_warnings():
            _w.simplefilter("ignore")
            records_df = pd.read_sql(_query, _conn)
        _conn.close()
        data_grid = mo.ui.table(
            records_df,
            selection="single",
            label="Select a record to graph:",
        )
        load_status = mo.md(
            f"Loaded **{len(records_df)}** DrivingInsights records from *{env_selector.value}*"
        )
    except Exception as _e:
        records_df = pd.DataFrame()
        data_grid  = mo.md(f"⚠️ **Connection error:** {_e}")
        load_status = mo.md("")

    return records_df, data_grid, load_status


@app.cell
def build_graph(data_grid, records_df, get_conn_str, env_selector, pyodbc, mo):
    import base64 as _b64
    from pyvis.network import Network

    # ── Selection guard ──────────────────────────────────────────────────────
    _has_sel = False
    if hasattr(data_grid, "value") and data_grid.value is not None:
        if hasattr(data_grid.value, "empty"):
            _has_sel = not data_grid.value.empty
        elif isinstance(data_grid.value, list):
            _has_sel = len(data_grid.value) > 0

    if not _has_sel:
        graph_output = mo.md("*Select a row above to generate the interactive tree.*")
    else:
        # ── Identify selected row ────────────────────────────────────────────
        if hasattr(data_grid.value, "iloc"):
            _sel_id  = int(data_grid.value.iloc[0]["id"])
            _sel_row = records_df[records_df["id"] == _sel_id].iloc[0]
        else:
            _sel_row = records_df.iloc[data_grid.value[0]]
            _sel_id  = int(_sel_row["id"])

        # ── Fetch full tree ──────────────────────────────────────────────────
        _conn = pyodbc.connect(get_conn_str(env_selector.value))
        _cur  = _conn.cursor()

        def _q1(sql, params=()):
            try:
                _cur.execute(sql, params)
                return _cur.fetchone()
            except Exception:
                return None

        def _qn(sql, params=()):
            try:
                _cur.execute(sql, params)
                return _cur.fetchall()
            except Exception:
                return []

        _ssk = _q1(
            "SELECT sdk_source_event_id, sentiance_user_id, source_time "
            "FROM SdkSourceEvent WHERE sentiance_eventos_id = ?", (_sel_id,)
        )
        _ssk_id = _ssk[0] if _ssk else None

        _dit = _q1(
            "SELECT driving_insights_trip_id, overall_score, distance_meters, "
            "       canonical_transport_event_id "
            "FROM DrivingInsightsTrip WHERE sdk_source_event_id = ?", (_ssk_id,)
        ) if _ssk_id else None
        _dit_id = _dit[0] if _dit else None

        _trip = _q1(
            "SELECT trip_id, transport_mode, start_time, end_time "
            "FROM Trip WHERE canonical_transport_event_id = ?", (_dit[3],)
        ) if _dit and _dit[3] else None

        _harsh = _qn("SELECT harsh_event_id, harsh_type, start_time FROM DrivingInsightsHarshEvent WHERE driving_insights_trip_id = ?", (_dit_id,)) if _dit_id else []
        _phone = _qn("SELECT phone_event_id, call_state, start_time FROM DrivingInsightsPhoneEvent WHERE driving_insights_trip_id = ?", (_dit_id,)) if _dit_id else []
        _call  = _qn("SELECT call_event_id, hands_free_state, start_time FROM DrivingInsightsCallEvent WHERE driving_insights_trip_id = ?", (_dit_id,)) if _dit_id else []
        _speed = _qn("SELECT speeding_event_id, start_time FROM DrivingInsightsSpeedingEvent WHERE driving_insights_trip_id = ?", (_dit_id,)) if _dit_id else []
        _wrong = _qn("SELECT wrong_way_event_id, start_time FROM DrivingInsightsWrongWayDrivingEvent WHERE driving_insights_trip_id = ?", (_dit_id,)) if _dit_id else []

        _conn.close()

        # ── Build pyvis graph ────────────────────────────────────────────────
        net = Network(
            height="680px",
            width="100%",
            directed=True,
            cdn_resources="in_line",
        )

        net.set_options("""
        {
          "layout": { "randomSeed": 0 },
          "physics": { "enabled": false },
          "nodes": {
            "shape": "box",
            "font": { "size": 14, "color": "white", "face": "monospace" },
            "margin": { "top": 10, "right": 14, "bottom": 10, "left": 14 },
            "borderWidth": 0,
            "shadow": { "enabled": true, "size": 6, "x": 2, "y": 2 }
          },
          "edges": {
            "arrows": { "to": { "enabled": true, "scaleFactor": 0.7 } },
            "color": { "color": "#888", "highlight": "#333" },
            "smooth": { "type": "cubicBezier", "roundness": 0.4 },
            "width": 1.8
          },
          "interaction": {
            "dragNodes": true,
            "dragView": true,
            "zoomView": true,
            "hover": true,
            "tooltipDelay": 150
          }
        }
        """)

        def _fmt_time(t):
            return str(t)[:16] if t else "—"

        def _add(nid, label, color, x, y, title=""):
            net.add_node(
                nid,
                label=label,
                color={"background": color, "border": color,
                       "highlight": {"background": color, "border": "#fff"}},
                x=x, y=y,
                physics=False,
                title=title or label,
            )

        # ── Collect leaf data first so we can compute x positions ────────────
        _leaves = []   # (nid, label, color, title)

        if _trip:
            _tmode = str(_trip[1]) if _trip[1] else "—"
            _leaves.append((
                "TRIP",
                f"Trip\nid: {_trip[0]}\nMode: {_tmode}\n{_fmt_time(_trip[2])}",
                "#1A9B8A",
                f"Trip\nid: {_trip[0]}\nMode: {_tmode}\nStart: {_fmt_time(_trip[2])}\nEnd: {_fmt_time(_trip[3])}",
            ))

        for r in _harsh:
            _leaves.append((
                f"HARSH_{r[0]}",
                f"HarshEvent\nid: {r[0]}\n{r[1] or '—'}",
                "#C0392B",
                f"HarshEvent\nid: {r[0]}\nType: {r[1] or '—'}\nTime: {_fmt_time(r[2])}",
            ))

        for r in _phone:
            _leaves.append((
                f"PHONE_{r[0]}",
                f"PhoneEvent\nid: {r[0]}\n{r[1] or '—'}",
                "#7D3C98",
                f"PhoneEvent\nid: {r[0]}\nState: {r[1] or '—'}\nTime: {_fmt_time(r[2])}",
            ))

        for r in _call:
            _leaves.append((
                f"CALL_{r[0]}",
                f"CallEvent\nid: {r[0]}\n{r[1] or '—'}",
                "#CB4E8E",
                f"CallEvent\nid: {r[0]}\nHands-free: {r[1] or '—'}\nTime: {_fmt_time(r[2])}",
            ))

        for r in _speed:
            _leaves.append((
                f"SPEED_{r[0]}",
                f"SpeedingEvent\nid: {r[0]}\n{_fmt_time(r[1])}",
                "#B8860B",
                f"SpeedingEvent\nid: {r[0]}\nTime: {_fmt_time(r[1])}",
            ))

        for r in _wrong:
            _leaves.append((
                f"WRONG_{r[0]}",
                f"WrongWayEvent\nid: {r[0]}\n{_fmt_time(r[1])}",
                "#784212",
                f"WrongWayDrivingEvent\nid: {r[0]}\nTime: {_fmt_time(r[1])}",
            ))

        # ── Compute positions ────────────────────────────────────────────────
        _Y = {0: 0, 1: 180, 2: 360, 3: 560}
        _x_gap = 230
        _n = max(len(_leaves), 1)
        _total_w = (_n - 1) * _x_gap

        # ── Add trunk nodes ──────────────────────────────────────────────────
        _add(
            "SE", f"SentianceEventos\nid: {_sel_id}",
            "#E8781A", x=0, y=_Y[0],
            title=f"SentianceEventos\nid: {_sel_id}\nuser: {_ssk[1] if _ssk else '—'}",
        )

        if _ssk:
            _add(
                "SSK", f"SdkSourceEvent\nid: {_ssk_id}",
                "#3A6BC9", x=0, y=_Y[1],
                title=f"SdkSourceEvent\nid: {_ssk_id}\nuser: {_ssk[1]}\ntime: {_fmt_time(_ssk[2])}",
            )
            net.add_edge("SE", "SSK")

        if _dit:
            _score = f"{float(_dit[1]):.3f}" if _dit[1] is not None else "N/A"
            _dist  = f"{float(_dit[2])/1000:.2f} km" if _dit[2] is not None else "N/A"
            _add(
                "DIT",
                f"DrivingInsightsTrip\nid: {_dit_id}\nScore: {_score}  |  {_dist}",
                "#2E8B57", x=0, y=_Y[2],
                title=f"DrivingInsightsTrip\nid: {_dit_id}\nScore: {_score}\nDist: {_dist}\ncanonical_id: {_dit[3]}",
            )
            net.add_edge("SSK", "DIT")

        # ── Add leaf nodes spread evenly at level 3 ──────────────────────────
        for i, (nid, label, color, title) in enumerate(_leaves):
            _x = int(-_total_w / 2 + i * _x_gap)
            _add(nid, label, color, x=_x, y=_Y[3], title=title)
            net.add_edge("DIT", nid)

        # ── Embed as iframe ──────────────────────────────────────────────────
        _html   = net.generate_html()
        _enc    = _b64.b64encode(_html.encode()).decode()
        graph_output = mo.Html(
            f'<iframe src="data:text/html;base64,{_enc}" '
            f'width="100%" height="700px" frameborder="0" '
            f'style="border-radius:6px;border:1px solid #ddd"></iframe>'
        )

    return (graph_output,)


@app.cell
def render_app(header, load_status, data_grid, graph_output, mo):
    final_layout = mo.vstack(
        [header, load_status, data_grid, mo.md("---"), graph_output]
    )
    final_layout
    return (final_layout,)


if __name__ == "__main__":
    app.run()
