"""
conftest.py — Shared pytest fixtures for the SentianceETL unit test suite.

The core problem: SentianceETL.__init__() reads env vars and raises ValueError
if they're missing. Unit tests don't need a DB, so we patch os.getenv to
return dummy values and never call connect().
"""

import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Fixture: etl
#   Returns a SentianceETL instance with all DB env vars stubbed out.
#   The conn / cursor are left as None — unit tests must not call them.
# ---------------------------------------------------------------------------

_FAKE_ENV = {
    "DB_SERVER": "localhost",
    "DB_PORT": "1433",
    "DB_USER": "sa",
    "DB_PASSWORD": "test",
    "DB_NAME": "VictaTMTK",
}


@pytest.fixture
def etl():
    """
    Provides a SentianceETL instance that is safe for unit tests.

    os.getenv is patched so __init__ sees valid-looking env values without
    requiring a real .env file. The instance is NOT connected to any DB.
    """
    with patch("os.getenv", side_effect=lambda key, default=None: _FAKE_ENV.get(key, default)):
        from sentiance_etl import SentianceETL
        instance = SentianceETL()
    return instance


# ---------------------------------------------------------------------------
# Fixture: mock_cursor
#   A MagicMock that records every execute() call. Used in Phase 2 tests
#   to verify parameter extraction without running actual SQL.
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_cursor():
    """
    Returns a MagicMock that mimics a pyodbc cursor.

    The fetchone() return value is configurable per test by setting
    mock_cursor.fetchone.return_value = (some_value,)
    """
    cursor = MagicMock()
    cursor.fetchone.return_value = (999,)   # default @@IDENTITY / SELECT result
    return cursor


@pytest.fixture
def etl_with_cursor(etl, mock_cursor):
    """
    Provides an ETL instance wired up to a mock_cursor so process_* methods
    can be called and their SQL parameters inspected.
    """
    etl.cursor = mock_cursor
    etl.conn = MagicMock()
    return etl
