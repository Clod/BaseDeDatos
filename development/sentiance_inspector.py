# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "marimo",
#     "pandas",
#     "pyodbc",
#     "python-dotenv",
# ]
# ///

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
        tuple: Contains required modules (json, pyodbc, pd, mo), the 
               environment dictionary (envs_dict), and the connection string helper (get_conn_str).
    """
    import os
    import json
    import pyodbc
    import pandas as pd
    import marimo as mo
    from dotenv import dotenv_values

    # Load environments safely
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    env_local = dotenv_values(os.path.join(root_dir, ".env"))
    env_rds = dotenv_values(os.path.join(root_dir, ".env.rds"))
    
    envs_dict = {"Local (Docker)": env_local}
    if env_rds and env_rds.get("DB_SERVER"):
        envs_dict["AWS RDS (Production)"] = env_rds
    
    def get_conn_str(env_name):
        """
        Builds a SQL Server ODBC connection string based on the selected environment.
        
        Args:
            env_name (str): The key from the 'envs_dict' dictionary (e.g., 'Local (Docker)').
            
        Returns:
            str: The fully formatted ODBC connection string.
        """
        env = envs_dict.get(env_name)
        return (f"DRIVER={{ODBC Driver 18 for SQL Server}};"
                f"SERVER={env.get('DB_SERVER')},{env.get('DB_PORT')};"
                f"DATABASE={env.get('DB_NAME')};"
                f"UID={env.get('DB_USER')};"
                f"PWD={env.get('DB_PASSWORD')};"
                f"Encrypt=yes;TrustServerCertificate=yes")
                
    return json, pyodbc, pd, mo, envs_dict, get_conn_str

@app.cell
def create_ui(mo, envs_dict):
    """
    Constructs the interactive UI controls for the dashboard.
    
    Args:
        mo (module): The marimo UI module.
        envs_dict (dict): Dictionary of available environments.
        
    Logic:
        Creates dropdowns for Environment selection, Event Type filtering, 
        and a number input for the query limit.
        
    Returns:
        tuple: (env_selector, limit_selector, tipo_selector, header) UI elements.
    """
    env_selector = mo.ui.dropdown(
        options=list(envs_dict.keys()),
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
def load_data(env_selector, limit_selector, tipo_selector, get_conn_str, pyodbc, pd, mo):
    """
    Fetches processed records from the database and populates an interactive data grid.
    
    Args:
        env_selector, limit_selector, tipo_selector (marimo.ui): User inputs.
        get_conn_str (callable): Function to get the ODBC string.
        pyodbc, pd, mo: Required modules.
        
    Logic:
        Builds a dynamic SQL SELECT query based on UI filters. Connects to the 
        selected database, loads data into a Pandas DataFrame, and wraps it in a 
        marimo.ui.table for row selection.
        
    Returns:
        tuple: (raw_df, data_grid, grid_status) where grid is the interactive UI component.
    """
    _current_conn_str = get_conn_str(env_selector.value)
    
    query = f"SELECT TOP {limit_selector.value} id, tipo, sentianceid, created_at, is_processed, json FROM SentianceEventos WHERE is_processed = 1"
    if tipo_selector.value != "All":
        query += f" AND tipo = '{tipo_selector.value}'"
    query += " ORDER BY id DESC"
    
    try:
        import warnings as _warnings
        _conn = pyodbc.connect(_current_conn_str)
        with _warnings.catch_warnings():
            _warnings.simplefilter("ignore", UserWarning)
            raw_df = pd.read_sql(query, _conn)
        _conn.close()
        
        display_df = raw_df[['id', 'tipo', 'sentianceid', 'created_at', 'is_processed']]
        data_grid = mo.ui.table(display_df, selection="single", label="Select a processed record to inspect:")
        grid_status = mo.md(f"Loaded {len(raw_df)} records from {env_selector.value}")
    except Exception as e:
        raw_df = pd.DataFrame()
        data_grid = mo.md(f"⚠️ **Error connecting to {env_selector.value}:** {e}")
        grid_status = mo.md("")
        
    return raw_df, data_grid, grid_status

@app.cell
def process_selection(data_grid, raw_df, json, mo, pyodbc, get_conn_str, env_selector):
    """
    Processes the selected row from the data grid and performs expected vs. actual validation.
    
    Args:
        data_grid (marimo.ui.table): The interactive table.
        raw_df (DataFrame): The underlying data.
        json, mo, pyodbc: Modules.
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
    _has_sel = False
    if hasattr(data_grid, "value") and data_grid.value is not None:
        if hasattr(data_grid.value, "empty"):
            _has_sel = not data_grid.value.empty
        elif isinstance(data_grid.value, list):
            _has_sel = len(data_grid.value) > 0

    if not _has_sel:
        inspector_content = mo.md("*Select a row from the table above to view details.*")
    else:
        if hasattr(data_grid.value, "iloc"):
            row = data_grid.value.iloc[0]
        else:
            row = raw_df.iloc[data_grid.value[0]]
        
        raw_id = row['id']
        tipo = row['tipo']
        payload = json.loads(row['json'])
        
        pretty_json = json.dumps(payload, indent=2)
        left_pane = mo.md(f"### Raw Payload (ID: {raw_id})\n```json\n{pretty_json}\n```")
        
        _current_conn_str = get_conn_str(env_selector.value)
        import warnings as _warnings
        with _warnings.catch_warnings():
            _warnings.simplefilter("ignore", UserWarning)

        _conn = pyodbc.connect(_current_conn_str)
        _cursor = _conn.cursor()
        
        def check_tree(table_name, count_column='*'):
            """
            Helper function to query actual record counts in domain tables.
            
            Args:
                table_name (str): The domain table to query.
                count_column (str): The column to count, defaults to '*'.
                
            Returns:
                int: The number of rows found, or -1 if an error occurred.
            """
            try:
                cursor.execute("SELECT source_event_id FROM SdkSourceEvent WHERE id = ?", (int(raw_id),))
                sid_row = cursor.fetchone()
                if not sid_row: return 0
                sid = sid_row[0]
                cursor.execute(f"SELECT COUNT({count_column}) FROM {table_name} WHERE source_event_id = ?", (sid,))
                return cursor.fetchone()[0]
            except Exception:
                return -1
                
        validation_nodes = []
        
        if tipo == 'DrivingInsights':
            audit_count = cursor.execute("SELECT COUNT(*) FROM SdkSourceEvent WHERE id = ?", (int(raw_id),)).fetchone()[0]
            validation_nodes.append(f"**Audit (SdkSourceEvent):** {'✅' if audit_count > 0 else '❌'} (Found: {audit_count})")
            
            di_count = check_tree("DrivingInsightsTrip")
            validation_nodes.append(f"**DrivingInsightsTrip:** {'✅' if di_count > 0 else '❌'} (Found: {di_count})")
            
            expected_harsh = len(payload.get('harshDrivingEvents', []))
            actual_harsh = check_tree("DrivingInsightsHarshEvent")
            validation_nodes.append(f"- **HarshEvents:** {'✅' if actual_harsh == expected_harsh else '❌'} (Exp: {expected_harsh}, Found: {actual_harsh})")
            
            expected_phone = len(payload.get('phoneUsageEvents', []))
            actual_phone = check_tree("DrivingInsightsPhoneEvent")
            validation_nodes.append(f"- **PhoneEvents:** {'✅' if actual_phone == expected_phone else '❌'} (Exp: {expected_phone}, Found: {actual_phone})")
            
            tid = payload.get('transportEvent', {}).get('id')
            trip_count = cursor.execute("SELECT COUNT(*) FROM Trip WHERE canonical_transport_event_id = ?", (tid,)).fetchone()[0]
            validation_nodes.append(f"**Central Trip Sync:** {'✅' if trip_count > 0 else '❌'} (Trip ID {tid})")
            
        elif tipo in ['UserContextUpdate', 'requestUserContext']:
            ctx = payload if tipo == 'requestUserContext' else payload.get('userContext', {})
            
            header_count = check_tree("UserContextHeader")
            validation_nodes.append(f"**UserContextHeader:** {'✅' if header_count > 0 else '❌'} (Found: {header_count})")
            
            expected_seg = len(ctx.get('activeSegments', []))
            actual_seg = check_tree("UserContextActiveSegmentDetail")
            validation_nodes.append(f"- **Active Segments:** {'✅' if actual_seg == expected_seg else '❌'} (Exp: {expected_seg}, Found: {actual_seg})")
            
            expected_ev = len(ctx.get('events', []))
            actual_ev = check_tree("UserContextEventDetail")
            validation_nodes.append(f"- **Context Events:** {'✅' if actual_ev == expected_ev else '❌'} (Exp: {expected_ev}, Found: {actual_ev})")
            
        elif tipo == 'TimelineEvents':
            events = payload if isinstance(payload, list) else payload.get('events', [])
            expected_ev = len(events)
            actual_ev = check_tree("TimelineEventHistory")
            validation_nodes.append(f"**TimelineEventHistory:** {'✅' if actual_ev == expected_ev else '❌'} (Exp: {expected_ev}, Found: {actual_ev})")
            
        else:
            validation_nodes.append(f"**Validation missing for type:** {tipo}")

        _conn.close()
        right_pane = mo.md(f"### Relational Tree Validation\n" + "\n".join(validation_nodes))
        inspector_content = mo.hstack([left_pane, right_pane], widths=[1, 1], gap=2)
        
    return inspector_content,

@app.cell
def render_app(header, grid_status, data_grid, inspector_content, mo):
    """
    Renders the final, top-to-bottom UI layout for the notebook.
    
    Args:
        header, grid_status, data_grid, inspector_content (marimo.ui): UI components.
        mo (module): The marimo module.
        
    Returns:
        tuple: The final vertical stack layout.
    """
    final_layout = mo.vstack([
        header,
        grid_status,
        data_grid,
        mo.md("---"),
        inspector_content
    ])
    final_layout  # Explicitly evaluate as the final expression to render it
    return final_layout,

if __name__ == "__main__":
    app.run()
