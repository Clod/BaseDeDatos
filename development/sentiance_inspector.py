"""
Sentiance Visual Regression Dashboard (Marimo Notebook)
=======================================================

DESCRIPTION:
This is an interactive Marimo notebook designed to function as a visual 
unit testing and regression tool for the Sentiance ETL pipeline.

PURPOSE/WHY:
- Regression Testing: Allows developers to verify that the ETL correctly 
  maps complex, nested JSON payloads into the relational domain schema.
- Debugging: Provides a clear side-by-side view of the raw input versus 
  the expected database output to easily spot missing or malformed data.
- Accessibility: Creates a UI-driven approach to exploring the database 
  without writing complex SQL JOIN queries manually.

WORKFLOW:
1. Connects to the database (Local Docker or AWS RDS via .env files).
2. Fetches a grid of recently processed records from SentianceEventos.
3. When a record is selected, it parses the JSON on the left pane.
4. On the right pane, it dynamically calculates expected record counts 
   (e.g., number of harsh events in the JSON) and compares them to actual 
   record counts found in the domain tables, displaying Pass/Fail indicators.

USAGE:
To run the dashboard in your browser:
    marimo run development/sentiance_inspector.py

To edit the notebook code interactively:
    marimo edit development/sentiance_inspector.py

AUTHOR: Claudio Grasso / AI Assistant
DATE: April 2026
"""

import marimo

__generated_with = "0.23.1"
app = marimo.App(width="full")

@app.cell
def load_dependencies():
    """
    Loads required Python modules and environment configurations.
    
    Logic:
        Parses the local '.env' and production '.env.rds' files to build
        a dictionary of available database environments. Defines a helper 
        function to generate ODBC connection strings.
        
    Returns:
        tuple: Contains required modules (_json, _pyodbc, _pd, mo), the 
               environment dictionary (envs), and the connection string helper (get_conn_str).
    """
    import os as _os
    import json as _json
    import pyodbc as _pyodbc
    import pandas as _pd
    import marimo as mo
    from dotenv import dotenv_values as _dotenv_values

    # Load environments
    _root_dir = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), ".."))
    _env_local = _dotenv_values(_os.path.join(_root_dir, ".env"))
    _env_rds = _dotenv_values(_os.path.join(_root_dir, ".env.rds"))
    
    envs = {"Local (Docker)": _env_local}
    if _env_rds and _env_rds.get("DB_SERVER"):
        envs["AWS RDS (Production)"] = _env_rds
    
    def get_conn_str(env_name):
        """
        Builds a SQL Server ODBC connection string based on the selected environment.
        
        Args:
            env_name (str): The key from the 'envs' dictionary (e.g., 'Local (Docker)').
            
        Returns:
            str: The fully formatted ODBC connection string.
        """
        _env = envs.get(env_name)
        return (f"DRIVER={{ODBC Driver 18 for SQL Server}};"
                f"SERVER={_env.get('DB_SERVER')},{_env.get('DB_PORT')};"
                f"DATABASE={_env.get('DB_NAME')};"
                f"UID={_env.get('DB_USER')};"
                f"PWD={_env.get('DB_PASSWORD')};"
                f"Encrypt=yes;TrustServerCertificate=yes")
                
    return _json, _pyodbc, _pd, mo, envs, get_conn_str

@app.cell
def create_ui(mo, envs):
    """
    Constructs the interactive UI controls for the dashboard.
    
    Args:
        mo (module): The marimo UI module.
        envs (dict): Dictionary of available environments.
        
    Logic:
        Creates dropdowns for Environment selection, Event Type filtering, 
        and a number input for the query limit.
        
    Returns:
        tuple: (env_selector, limit_selector, tipo_selector, header) UI elements.
    """
    env_selector = mo.ui.dropdown(
        options=list(envs.keys()),
        value="Local (Docker)",
        label="Select Environment: "
    )
    
    limit_selector = mo.ui.number(
        start=10, stop=500, value=50, step=10, 
        label="Records to Load: "
    )
    
    tipo_selector = mo.ui.dropdown(
        options=["All", "DrivingInsights", "UserContextUpdate", "requestUserContext", "TimelineEvents", "VehicleCrash", "SDKStatus", "UserMetadata", "UserActivity", "TechnicalEvent"],
        value="All",
        label="Filter by Event Type: "
    )
    
    header = mo.md(f"""
    # 🚗 Sentiance Visual Regression Dashboard
    *A tool to inspect ETL domain projection and verify data integrity.*
    
    **Controls:**
    {env_selector} | {tipo_selector} | {limit_selector}
    ---
    """)
    return env_selector, limit_selector, tipo_selector, header

@app.cell
def load_data(env_selector, limit_selector, tipo_selector, get_conn_str, _pyodbc, _pd, mo):
    """
    Fetches processed records from the database and populates an interactive data grid.
    
    Args:
        env_selector, limit_selector, tipo_selector (marimo.ui): User inputs.
        get_conn_str (callable): Function to get the ODBC string.
        _pyodbc, _pd, mo: Required modules.
        
    Logic:
        Builds a dynamic SQL SELECT query based on UI filters. Connects to the 
        selected database, loads data into a Pandas DataFrame, and wraps it in a 
        marimo.ui.table for row selection.
        
    Returns:
        tuple: (df, grid, grid_status) where grid is the interactive UI component.
    """
    _conn_str = get_conn_str(env_selector.value)
    
    _query = f"SELECT TOP {limit_selector.value} id, tipo, sentianceid, created_at, is_processed, json FROM SentianceEventos WHERE is_processed = 1"
    if tipo_selector.value != "All":
        _query += f" AND tipo = '{tipo_selector.value}'"
    _query += " ORDER BY id DESC"
    
    try:
        _conn = _pyodbc.connect(_conn_str)
        df = _pd.read_sql(_query, _conn)
        _conn.close()
        
        _display_df = df[['id', 'tipo', 'sentianceid', 'created_at', 'is_processed']]
        grid = mo.ui.table(_display_df, selection="single", label="Select a processed record to inspect:")
        grid_status = mo.md(f"Loaded {len(df)} records from {env_selector.value}")
    except Exception as _e:
        df = None
        grid = mo.md(f"⚠️ **Error connecting to {env_selector.value}:** {_e}")
        grid_status = mo.md("")
        
    return df, grid, grid_status

@app.cell
def process_selection(grid, df, _json, mo, _pyodbc, get_conn_str, env_selector):
    """
    Processes the selected row from the data grid and performs expected vs. actual validation.
    
    Args:
        grid (marimo.ui.table): The interactive table.
        df (DataFrame): The underlying data.
        _json, mo, _pyodbc: Modules.
        get_conn_str, env_selector: Environment dependencies.
        
    Logic:
        When a user clicks a row, this function parses the raw JSON. It displays 
        the formatted JSON in the left pane. On the right pane, it dynamically 
        queries the child domain tables (like DrivingInsightsHarshEvent) to verify 
        that the number of records found exactly matches the number of elements 
        in the JSON array.
        
    Returns:
        tuple: A marimo layout containing the side-by-side JSON and validation panes.
    """
    if not hasattr(grid, "value") or not grid.value:
        content = mo.md("*Select a row from the table above to view details.*")
    else:
        _selected_idx = grid.value[0]
        _row = df.iloc[_selected_idx]
        
        _raw_id = _row['id']
        _tipo = _row['tipo']
        _payload = _json.loads(_row['json'])
        
        _pretty_json = _json.dumps(_payload, indent=2)
        _left_pane = mo.md(f"### Raw Payload (ID: {_raw_id})\n```json\n{_pretty_json}\n```")
        
        _conn_str = get_conn_str(env_selector.value)
        _conn = _pyodbc.connect(_conn_str)
        _cursor = _conn.cursor()
        
        def check_tree(table_name, count_column='*'):
            """
            Helper function to query actual record counts in domain tables.
            
            Args:
                table_name (str): The domain table to query (e.g., 'DrivingInsightsTrip').
                count_column (str): The column to count, defaults to '*'.
                
            Returns:
                int: The number of rows found, or -1 if an error occurred.
            """
            try:
                _cursor.execute("SELECT source_event_id FROM SdkSourceEvent WHERE id = ?", (int(_raw_id),))
                _sid_row = _cursor.fetchone()
                if not _sid_row: return 0
                _sid = _sid_row[0]
                _cursor.execute(f"SELECT COUNT({count_column}) FROM {table_name} WHERE source_event_id = ?", (_sid,))
                return _cursor.fetchone()[0]
            except Exception:
                return -1
                
        _validation_nodes = []
        
        if _tipo == 'DrivingInsights':
            _audit_count = _cursor.execute("SELECT COUNT(*) FROM SdkSourceEvent WHERE id = ?", (int(_raw_id),)).fetchone()[0]
            _validation_nodes.append(f"**Audit (SdkSourceEvent):** {'✅' if _audit_count > 0 else '❌'} (Found: {_audit_count})")
            
            _di_count = check_tree("DrivingInsightsTrip")
            _validation_nodes.append(f"**DrivingInsightsTrip:** {'✅' if _di_count > 0 else '❌'} (Found: {_di_count})")
            
            _expected_harsh = len(_payload.get('harshDrivingEvents', []))
            _actual_harsh = check_tree("DrivingInsightsHarshEvent")
            _validation_nodes.append(f"- **HarshEvents:** {'✅' if _actual_harsh == _expected_harsh else '❌'} (Exp: {_expected_harsh}, Found: {_actual_harsh})")
            
            _expected_phone = len(_payload.get('phoneUsageEvents', []))
            _actual_phone = check_tree("DrivingInsightsPhoneEvent")
            _validation_nodes.append(f"- **PhoneEvents:** {'✅' if _actual_phone == _expected_phone else '❌'} (Exp: {_expected_phone}, Found: {_actual_phone})")
            
            _tid = _payload.get('transportEvent', {}).get('id')
            _trip_count = _cursor.execute("SELECT COUNT(*) FROM Trip WHERE canonical_transport_event_id = ?", (_tid,)).fetchone()[0]
            _validation_nodes.append(f"**Central Trip Sync:** {'✅' if _trip_count > 0 else '❌'} (Trip ID {_tid})")
            
        elif _tipo in ['UserContextUpdate', 'requestUserContext']:
            _ctx = _payload if _tipo == 'requestUserContext' else _payload.get('userContext', {})
            
            _header_count = check_tree("UserContextHeader")
            _validation_nodes.append(f"**UserContextHeader:** {'✅' if _header_count > 0 else '❌'} (Found: {_header_count})")
            
            _expected_seg = len(_ctx.get('activeSegments', []))
            _actual_seg = check_tree("UserContextActiveSegmentDetail")
            _validation_nodes.append(f"- **Active Segments:** {'✅' if _actual_seg == _expected_seg else '❌'} (Exp: {_expected_seg}, Found: {_actual_seg})")
            
            _expected_ev = len(_ctx.get('events', []))
            _actual_ev = check_tree("UserContextEventDetail")
            _validation_nodes.append(f"- **Context Events:** {'✅' if _actual_ev == _expected_ev else '❌'} (Exp: {_expected_ev}, Found: {_actual_ev})")
            
        elif _tipo == 'TimelineEvents':
            _events = _payload if isinstance(_payload, list) else _payload.get('events', [])
            _expected_ev = len(_events)
            _actual_ev = check_tree("TimelineEventHistory")
            _validation_nodes.append(f"**TimelineEventHistory:** {'✅' if _actual_ev == _expected_ev else '❌'} (Exp: {_expected_ev}, Found: {_actual_ev})")
            
        else:
            _validation_nodes.append(f"**Validation missing for type:** {_tipo}")

        _conn.close()
        _right_pane = mo.md(f"### Relational Tree Validation\n" + "\n".join(_validation_nodes))
        content = mo.hstack([_left_pane, _right_pane], widths=[1, 1], gap=2)
        
    return content,

@app.cell
def render(header, grid_status, grid, content, mo):
    """
    Renders the final, top-to-bottom UI layout for the notebook.
    
    Args:
        header, grid_status, grid, content (marimo.ui): UI components from previous cells.
        mo (module): The marimo module.
        
    Returns:
        tuple: The final vertical stack layout to be displayed in the browser.
    """
    _layout = mo.vstack([
        header,
        grid_status,
        grid,
        mo.md("---"),
        content
    ])
    return _layout,

if __name__ == "__main__":
    app.run()
