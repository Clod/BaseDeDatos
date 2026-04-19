# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "marimo",
#   "pyodbc",
#   "deepdiff",
#   "python-dotenv",
# ]
# ///

import marimo

__generated_with = "0.12.0"
app = marimo.App(width="full")


@app.cell
def _():
    import marimo as mo
    import json
    import pyodbc
    from dotenv import load_dotenv
    from deepdiff import DeepDiff
    import os

    load_dotenv()


@app.cell
def _():
    server = os.getenv("DB_SERVER")
    port = os.getenv("DB_PORT")
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")
    db = os.getenv("DB_NAME")

    conn_str = f"DRIVER={{ODBC Driver 18 for SQL Server}};SERVER={server},{port};DATABASE={db};UID={user};PWD={password};Encrypt=yes;TrustServerCertificate=yes"
    conn = pyodbc.connect(conn_str)
    cursor = conn.cursor()


@app.cell
def _(mo):
    event_type = mo.ui.dropdown(
        value="DrivingInsights",
        options=[
            "DrivingInsights",
            "DrivingInsightsHarshEvents",
            "DrivingInsightsPhoneEvents",
            "DrivingInsightsCallEvents",
            "DrivingInsightsSpeedingEvents",
            "DrivingInsightsWrongWayDrivingEvents",
            "UserContextUpdate",
            "requestUserContext",
            "TimelineEvents",
        ],
        label="Tipo de evento",
    )
    record_id = mo.ui.number(
        value=1,
        start=1,
        label="ID del registro",
    )
    event_type, record_id


@app.cell
def _(cursor, event_type, record_id, mo):
    cursor.execute(
        "SELECT id, sentianceid, json, tipo FROM SentianceEventos WHERE tipo = ? AND id = ?",
        (event_type.value, record_id.value),
    )
    source_row = cursor.fetchone()

    if source_row is None:
        mo.stop(True, mo.callout(mo.md("No se encontró el registro"), kind="warn"))

    raw_json = source_row[2] if source_row else None
    sentiance_user = source_row[1] if source_row else None


@app.cell
def _(mo, raw_json):
    try:
        payload = json.loads(raw_json) if raw_json else {}
    except Exception as e:
        mo.stop(True, mo.callout(mo.md(f"Error: {e}"), kind="danger"))
    payload


@app.cell
def _(cursor, payload, mo):
    user_id = payload.get("userId") if isinstance(payload, dict) else ""

    cursor.execute(
        "SELECT TOP 1 tipo FROM SentianceEventos WHERE sentianceid = ? AND tipo LIKE 'DrivingInsights%'",
        (user_id,),
    )
    di_row = cursor.fetchone()
    di_type = di_row[0] if di_row else "DrivingInsights"

    table_lookup = {
        "DrivingInsights": "DrivingInsightsTrip",
        "DrivingInsightsHarshEvents": "DrivingInsightsHarshEvent",
        "DrivingInsightsPhoneEvents": "DrivingInsightsPhoneEvent",
        "DrivingInsightsCallEvents": "DrivingInsightsCallEvent",
        "DrivingInsightsSpeedingEvents": "DrivingInsightsSpeedingEvent",
        "DrivingInsightsWrongWayDrivingEvents": "DrivingInsightsWrongWayDrivingEvent",
    }

    db_table = table_lookup.get(di_type, "DrivingInsightsTrip")


@app.cell
def _(cursor, sentiance_user, db_table, mo):
    cursor.execute(
        f"SELECT * FROM {db_table} WHERE sentiance_user_id = ?",
        (sentiance_user,),
    )
    col_names = [c[0] for c in cursor.description] if cursor.description else []
    table_rows = cursor.fetchall()

    if not table_rows:
        mo.stop(True, mo.callout(mo.md(f"No hay registros en {db_table}"), kind="warn"))

    db_data = [dict(zip(col_names, r)) for r in table_rows]


@app.cell
def _(payload, mo):
    def simplify_json(node):
        if isinstance(node, dict):
            result = {}
            for k, v in node.items():
                if k in [
                    "transportEvent",
                    "safetyScores",
                    "harshDrivingEvents",
                    "phoneUsageEvents",
                    "callWhileMovingEvents",
                    "speedingEvents",
                ]:
                    result[k] = simplify_json(v)
                elif k in ["waypoints", "transportTags"]:
                    result[k] = f"<{type(v).__name__}>" if v else None
                elif v is not None:
                    result[k] = v
            return result
        elif isinstance(node, list):
            return [simplify_json(i) for i in node[:3]]
        return node

    json_simp = simplify_json(payload)


@app.cell
def _(db_data, mo):
    def simplify_db(node):
        result = {}
        for k, v in node.items():
            if k.endswith("_json"):
                result[k] = "<compressed>" if v else None
            elif v is not None:
                result[k] = v
        return result

    db_simp = [simplify_db(r) for r in db_data]


@app.cell
def _():
    def make_json_tree(node, depth=0):
        if depth > 3:
            return "[max]"
        if not node:
            return {}
        if isinstance(node, dict):
            return {
                str(k): make_json_tree(v, depth + 1)
                for k, v in list(node.items())[:10]
                if v is not None
            }
        if isinstance(node, list):
            return [make_json_tree(i, depth + 1) for i in node[:3]]
        return str(node)[:50]

    def make_db_tree(node, depth=0):
        if depth > 3:
            return "[max]"
        if not node:
            return {}
        if isinstance(node, dict):
            return {
                str(k): make_db_tree(v, depth + 1)
                for k, v in list(node.items())[:15]
                if v is not None
            }
        if isinstance(node, list):
            return [make_db_tree(i, depth + 1) for i in node[:3]]
        return str(node)[:80]

    json_tree_fn = make_json_tree
    db_tree_fn = make_db_tree


@app.cell
def _(DeepDiff, db_simp, json_simp):
    diff = DeepDiff(json_simp, db_simp, ignore_order=True, report_repetition=True)

    diff_view = mo.callout(mo.tree(dict(diff)) if diff else mo.md("✅ identical"))


@app.cell
def _(db_tree_fn, diff_view, json_simp, json_tree_fn, mo, db_simp):
    mo.vstack(
        [
            mo.hstack(
                [
                    mo.vstack(
                        [
                            mo.md("### 📄 JSON (SentianceEventos)"),
                            mo.tree([json_tree_fn(json_simp)], label="JSON"),
                        ]
                    ),
                    mo.vstack(
                        [
                            mo.md("### 🗄️ DB (Tablas)"),
                            mo.tree([db_tree_fn(db_simp[0])], label="DB")
                            if db_simp
                            else mo.md("*empty*"),
                        ]
                    ),
                ],
                widths="equal",
            ),
            mo.md("---"),
            mo.md("### 🔍 Diff"),
            diff_view,
        ]
    )


if __name__ == "__main__":
    app.run()
