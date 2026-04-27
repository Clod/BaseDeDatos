"""
Sentiance ETL Batch Validator
=============================

DESCRIPTION:
Headless batch validator for the Sentiance ETL pipeline. Iterates all
processed records in SentianceEventos and runs the same validation rules
as the interactive sentiance_inspector.py dashboard, writing pass/fail
results to stdout.

VALIDATION RULES:
For each record type the validator compares expected counts derived from
the raw JSON against actual row counts in the domain tables:

  DrivingInsights             → SdkSourceEvent, DrivingInsightsTrip, Trip,
                                HarshEvent, PhoneEvent, SpeedingEvent,
                                CallEvent, WrongWayDrivingEvent

  DrivingInsights*Events      → DrivingInsightsTrip (parent must exist),
                                child table row count vs len(payload["events"])

  UserContextUpdate /
  requestUserContext          → UserContextHeader, ActiveSegmentDetail,
                                ContextEventDetail, HomeHistory, WorkHistory,
                                UpdateCriteria, Trip sync per IN_TRANSPORT
                                event (isProvisional=false → must be in Trip;
                                isProvisional=true → must NOT be in Trip)

  TimelineEvents / TimelineUpdate → TimelineEventHistory row count vs
                                    len(payload["events"])

  VehicleCrash                → VehicleCrashEvent
  SDKStatus                   → SdkStatusHistory
  UserActivity                → UserActivityHistory
  TechnicalEvent              → TechnicalEventHistory
  UserMetadata                → UserMetadata

USAGE:
    # Validate all processed records against local Docker DB:
    python development/run_inspector_batch.py

    # Limit to the first N records (useful for quick smoke tests):
    python development/run_inspector_batch.py --limit 200

    # Run against AWS RDS (reads .env.rds):
    python development/run_inspector_batch.py --env rds

    # Combined:
    python development/run_inspector_batch.py --env rds --limit 500

OUTPUT FORMAT:
    [i/total] PASS|FAIL  id=<id>  <tipo>
        ✅ <validation message>
        ❌ <validation message>
    ...
    ══════════════════════════════════════════════════════════════
    BATCH COMPLETE
    Total   : 312
    Pass    : 298  (95.5%)
    Fail    :  14  ( 4.5%)
    Errors  :   0
    ══════════════════════════════════════════════════════════════

AUTHOR: Claudio Grasso / AI Assistant
DATE: April 2026
"""

import os
import json
import sys
import pyodbc
from dotenv import dotenv_values


def _build_conn_str(env="local"):
    """Builds the ODBC connection string from the appropriate .env file.

    Args:
        env: 'local' reads .env; 'rds' reads .env.rds.

    Returns:
        str: fully formatted ODBC connection string.
    """
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    env_file = ".env.rds" if env == "rds" else ".env"
    cfg = dotenv_values(os.path.join(root, env_file))
    return (
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"SERVER={cfg['DB_SERVER']},{cfg['DB_PORT']};"
        f"DATABASE={cfg['DB_NAME']};"
        f"UID={cfg['DB_USER']};"
        f"PWD={cfg['DB_PASSWORD']};"
        f"Encrypt=yes;TrustServerCertificate=yes"
    )


def validate_record(cursor, raw_id, tipo, payload, sentianceid):
    """Run all validations for one SentianceEventos record.

    Resolves expected counts from the raw JSON payload and compares them
    against actual row counts in the domain tables via the cursor.

    Args:
        cursor:      open pyodbc cursor (shared for the whole batch run).
        raw_id:      SentianceEventos.id (int).
        tipo:        payload type string (e.g. 'DrivingInsights').
        payload:     parsed JSON dict.
        sentianceid: Sentiance user ID string.

    Returns:
        list[str]: one line per check, each starting with ✅, ❌, or ⚠️.
    """
    results = []

    def _check_tree(table_name, count_column="*", use_payload_id=False):
        try:
            cursor.execute(
                "SELECT sdk_source_event_id FROM SdkSourceEvent WHERE sentiance_eventos_id = ?",
                (int(raw_id),),
            )
            sid_row = cursor.fetchone()
            if not sid_row:
                return 0
            sid = sid_row[0]
            if use_payload_id:
                cursor.execute(
                    "SELECT user_context_payload_id FROM UserContextHeader WHERE sdk_source_event_id = ?",
                    (sid,),
                )
                ph_row = cursor.fetchone()
                if not ph_row:
                    return 0
                cursor.execute(
                    f"SELECT COUNT({count_column}) FROM {table_name} WHERE user_context_payload_id = ?",
                    (ph_row[0],),
                )
            elif table_name.startswith("DrivingInsights"):
                cursor.execute(
                    "SELECT driving_insights_trip_id FROM DrivingInsightsTrip WHERE sdk_source_event_id = ?",
                    (sid,),
                )
                trip_row = cursor.fetchone()
                if not trip_row:
                    return 0
                cursor.execute(
                    f"SELECT COUNT({count_column}) FROM {table_name} WHERE driving_insights_trip_id = ?",
                    (trip_row[0],),
                )
            else:
                cursor.execute(
                    f"SELECT COUNT({count_column}) FROM {table_name} WHERE sdk_source_event_id = ?",
                    (sid,),
                )
            return cursor.fetchone()[0]
        except Exception:
            return -1

    def _ok(cond, msg):
        results.append(f"{'✅' if cond else '❌'} {msg}")

    if tipo == "DrivingInsights":
        audit = cursor.execute(
            "SELECT COUNT(*) FROM SdkSourceEvent WHERE sentiance_eventos_id = ?",
            (int(raw_id),),
        ).fetchone()[0]
        _ok(audit > 0, f"SdkSourceEvent: found {audit}")
        di = _check_tree("DrivingInsightsTrip")
        _ok(di > 0, f"DrivingInsightsTrip: found {di}")
        for label, table in [
            ("HarshEvent",          "DrivingInsightsHarshEvent"),
            ("PhoneEvent",          "DrivingInsightsPhoneEvent"),
            ("SpeedingEvent",       "DrivingInsightsSpeedingEvent"),
            ("CallEvent",           "DrivingInsightsCallEvent"),
            ("WrongWayDrivingEvent","DrivingInsightsWrongWayDrivingEvent"),
        ]:
            n = _check_tree(table)
            _ok(n >= 0, f"{label}: found {n}")
        tid = payload.get("transportEvent", {}).get("id")
        tc = cursor.execute(
            "SELECT COUNT(*) FROM Trip WHERE canonical_transport_event_id = ?", (tid,)
        ).fetchone()[0]
        _ok(tc > 0, f"Central Trip Sync (id={tid}): found {tc}")

    elif tipo in ("UserContextUpdate", "requestUserContext"):
        ctx = payload if tipo == "requestUserContext" else payload.get("userContext", {})
        _ok(_check_tree("UserContextHeader") > 0,
            f"UserContextHeader: found {_check_tree('UserContextHeader')}")
        exp_seg = len(ctx.get("activeSegments", []))
        act_seg = _check_tree("UserContextActiveSegmentDetail", use_payload_id=True)
        _ok(act_seg == exp_seg, f"ActiveSegments: exp {exp_seg}, found {act_seg}")
        exp_ev = len(ctx.get("events", []))
        act_ev = _check_tree("UserContextEventDetail", use_payload_id=True)
        _ok(act_ev == exp_ev, f"ContextEvents: exp {exp_ev}, found {act_ev}")
        home = _check_tree("UserHomeHistory", use_payload_id=True)
        work = _check_tree("UserWorkHistory", use_payload_id=True)
        crit = _check_tree("UserContextUpdateCriteria", use_payload_id=True)
        results.append(f"  HomeHistory={home}  WorkHistory={work}  Criteria={crit}")
        for tev in [e for e in ctx.get("events", []) if str(e.get("type", "")).upper() == "IN_TRANSPORT"]:
            tid = tev.get("id")
            if not tid:
                continue
            provisional = bool(tev.get("isProvisional", False))
            tc = cursor.execute(
                "SELECT COUNT(*) FROM Trip WHERE canonical_transport_event_id = ?", (tid,)
            ).fetchone()[0]
            if provisional:
                _ok(tc == 0, f"Trip provisional must NOT be in Trip (id={tid}): found {tc}")
            else:
                _ok(tc > 0, f"Trip final must be in Trip (id={tid}): found {tc}")

    elif tipo in ("TimelineEvents", "TimelineUpdate"):
        events = payload if isinstance(payload, list) else payload.get("events", [])
        act = _check_tree("TimelineEventHistory")
        _ok(act == len(events), f"TimelineEventHistory: exp {len(events)}, found {act}")

    elif tipo in (
        "DrivingInsightsHarshEvents",
        "DrivingInsightsPhoneEvents",
        "DrivingInsightsCallEvents",
        "DrivingInsightsSpeedingEvents",
        "DrivingInsightsWrongWayDrivingEvents",
    ):
        _table_map = {
            "DrivingInsightsHarshEvents":          "DrivingInsightsHarshEvent",
            "DrivingInsightsPhoneEvents":           "DrivingInsightsPhoneEvent",
            "DrivingInsightsCallEvents":            "DrivingInsightsCallEvent",
            "DrivingInsightsSpeedingEvents":        "DrivingInsightsSpeedingEvent",
            "DrivingInsightsWrongWayDrivingEvents": "DrivingInsightsWrongWayDrivingEvent",
        }
        target = _table_map[tipo]
        transport_id = payload.get("transportId")
        exp = len(payload.get("events", []))
        if not transport_id:
            results.append(f"⚠️ {target}: no transportId in payload")
        else:
            try:
                di_row = cursor.execute(
                    "SELECT driving_insights_trip_id FROM DrivingInsightsTrip "
                    "WHERE canonical_transport_event_id = ? AND sentiance_user_id = ?",
                    (transport_id, sentianceid),
                ).fetchone()
                if not di_row:
                    results.append(
                        f"❌ {target}: parent DrivingInsightsTrip not found (transportId={transport_id})"
                    )
                else:
                    act = cursor.execute(
                        f"SELECT COUNT(*) FROM {target} WHERE driving_insights_trip_id = ?",
                        (di_row[0],),
                    ).fetchone()[0]
                    _ok(act == exp, f"{target}: exp {exp}, found {act}")
            except Exception as ex:
                results.append(f"⚠️ {target}: {ex}")

    elif tipo == "VehicleCrash":
        n = _check_tree("VehicleCrashEvent")
        _ok(n > 0, f"VehicleCrashEvent: found {n}")

    elif tipo == "SDKStatus":
        n = _check_tree("SdkStatusHistory")
        _ok(n > 0, f"SdkStatusHistory: found {n}")

    elif tipo == "UserActivity":
        n = _check_tree("UserActivityHistory")
        _ok(n > 0, f"UserActivityHistory: found {n}")

    elif tipo == "TechnicalEvent":
        n = _check_tree("TechnicalEventHistory")
        _ok(n > 0, f"TechnicalEventHistory: found {n}")

    elif tipo == "UserMetadata":
        n = cursor.execute(
            "SELECT COUNT(*) FROM UserMetadata WHERE sentiance_user_id = ?",
            (payload.get("sentiance_user_id") or sentianceid,),
        ).fetchone()[0]
        _ok(n > 0, f"UserMetadata: found {n}")

    else:
        results.append(f"⚠️ no validator for tipo={tipo}")

    return results


def run_batch(limit=None, env="local"):
    """Iterate all processed SentianceEventos records and print validation results.

    Opens a single connection, fetches all qualifying rows, calls
    validate_record for each, and prints a summary at the end.

    Args:
        limit: maximum number of records to process (None = all).
        env:   'local' (reads .env) or 'rds' (reads .env.rds).
    """
    conn = pyodbc.connect(_build_conn_str(env))
    cursor = conn.cursor()

    top_clause = f"TOP {limit} " if limit else ""
    cursor.execute(
        f"SELECT {top_clause}id, tipo, sentianceid, json "
        f"FROM SentianceEventos WHERE is_processed = 1 ORDER BY id"
    )
    rows = cursor.fetchall()
    total = len(rows)

    pass_count = fail_count = error_count = 0
    print(f"\n{'═'*60}")
    print(f"  SENTIANCE BATCH VALIDATOR   ({total} records, env={env})")
    print(f"{'═'*60}")

    for i, (raw_id, tipo, sentianceid, raw_json) in enumerate(rows, 1):
        try:
            payload = json.loads(raw_json)
            results = validate_record(cursor, raw_id, tipo, payload, sentianceid)
            has_fail = any(r.startswith("❌") for r in results)
            status = "FAIL" if has_fail else "PASS"
            print(f"\n[{i}/{total}] {status}  id={raw_id}  {tipo}")
            for r in results:
                print(f"    {r}")
            if has_fail:
                fail_count += 1
            else:
                pass_count += 1
        except Exception as ex:
            error_count += 1
            print(f"\n[{i}/{total}] ERROR  id={raw_id}  {tipo}")
            print(f"    ⚠️  {ex}")

    conn.close()
    print(f"\n{'═'*60}")
    print(f"  BATCH COMPLETE")
    print(f"  Total   : {total}")
    if total:
        print(f"  Pass    : {pass_count}  ({100 * pass_count / total:.1f}%)")
        print(f"  Fail    : {fail_count}  ({100 * fail_count / total:.1f}%)")
        print(f"  Errors  : {error_count}")
    print(f"{'═'*60}\n")


if __name__ == "__main__":
    args = sys.argv[1:]
    limit = None
    env = "local"
    if "--limit" in args:
        limit = int(args[args.index("--limit") + 1])
    if "--env" in args:
        env = args[args.index("--env") + 1]
    run_batch(limit=limit, env=env)
