"""
test_user_organization.py — Tests for UserOrganization multi-tenancy support.

Verifies that process_metadata() routes 'organizacion' labels to
_upsert_user_organization() and that the MERGE parameters are correct.
"""

import pytest
from unittest.mock import call, MagicMock


def _calls(mock_cursor):
    return [c.args for c in mock_cursor.execute.call_args_list]


# ---------------------------------------------------------------------------
# process_metadata — routing
# ---------------------------------------------------------------------------


def test_organizacion_label_triggers_upsert(etl_with_cursor):
    etl = etl_with_cursor
    etl.process_metadata("user-1", {"label": "organizacion", "value": "ClienteA"})

    sqls = [c[0] for c in _calls(etl.cursor)]
    assert any("UserMetadata" in s for s in sqls), "should INSERT into UserMetadata"
    assert any("UserOrganization" in s for s in sqls), "should MERGE into UserOrganization"


def test_other_label_does_not_trigger_upsert(etl_with_cursor):
    etl = etl_with_cursor
    etl.process_metadata("user-1", {"label": "vehicle_type", "value": "CAR"})

    sqls = [c[0] for c in _calls(etl.cursor)]
    assert any("UserMetadata" in s for s in sqls)
    assert not any("UserOrganization" in s for s in sqls)


def test_organizacion_label_is_case_insensitive(etl_with_cursor):
    etl = etl_with_cursor
    etl.process_metadata("user-1", {"label": "Organizacion", "value": "ClienteB"})

    sqls = [c[0] for c in _calls(etl.cursor)]
    assert any("UserOrganization" in s for s in sqls)


def test_missing_value_does_not_trigger_upsert(etl_with_cursor):
    etl = etl_with_cursor
    etl.process_metadata("user-1", {"label": "organizacion", "value": None})

    sqls = [c[0] for c in _calls(etl.cursor)]
    assert not any("UserOrganization" in s for s in sqls)


# ---------------------------------------------------------------------------
# _upsert_user_organization — parameters
# ---------------------------------------------------------------------------


def test_upsert_passes_correct_params(etl_with_cursor):
    etl = etl_with_cursor
    etl._upsert_user_organization("user-abc", "ClienteX")

    args = etl.cursor.execute.call_args.args
    sql, params = args[0], args[1]
    assert "MERGE UserOrganization" in sql
    assert "WHEN MATCHED" in sql
    assert "WHEN NOT MATCHED" in sql
    # params: (uid for USING, org for UPDATE, uid for INSERT, org for INSERT)
    assert params == ("user-abc", "ClienteX", "user-abc", "ClienteX")


def test_upsert_sql_resets_activo_and_hasta(etl_with_cursor):
    etl = etl_with_cursor
    etl._upsert_user_organization("user-abc", "ClienteY")

    sql = etl.cursor.execute.call_args.args[0]
    assert "activo = 1" in sql
    assert "hasta = NULL" in sql
