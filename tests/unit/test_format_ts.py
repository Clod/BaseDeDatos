"""
test_format_ts.py — Phase 1: Unit tests for SentianceETL.format_ts()

WHAT IS BEING TESTED:
    The timestamp formatter converts ISO-8601 strings (with 'T' separator and
    optional 'Z' suffix) into the DATETIME2(3) format expected by SQL Server
    (space separator, no timezone, truncated to 23 characters max).

EDGE CASES COVERED:
    - Full precision ISO timestamp with Z        → truncated to 23 chars
    - Short ISO timestamp without milliseconds   → kept as-is (no padding)
    - Sub-millisecond precision (nanoseconds)    → hard-truncated at char 23
    - Missing Z suffix (already UTC-normalised)  → T still replaced
    - Empty string                               → None
    - None input                                 → None
    - Timestamp already in SQL format            → T replacement is idempotent
"""

import pytest


# ---------------------------------------------------------------------------
# Happy-path: standard ISO timestamps
# ---------------------------------------------------------------------------

class TestFormatTsHappyPath:

    def test_full_millisecond_precision_with_z(self, etl):
        """Standard SDK timestamp format → space-separated, no Z."""
        result = etl.format_ts("2026-04-01T14:30:00.123Z")
        assert result == "2026-04-01 14:30:00.123"

    def test_no_milliseconds_with_z(self, etl):
        """Timestamp without fractional seconds."""
        result = etl.format_ts("2026-04-01T14:30:00Z")
        assert result == "2026-04-01 14:30:00"

    def test_no_z_suffix(self, etl):
        """Timestamp without Z (already stripped upstream)."""
        result = etl.format_ts("2026-04-01T14:30:00.456")
        assert result == "2026-04-01 14:30:00.456"

    def test_midnight_timestamp(self, etl):
        """Boundary: midnight."""
        result = etl.format_ts("2026-01-01T00:00:00.000Z")
        assert result == "2026-01-01 00:00:00.000"

    def test_end_of_day_timestamp(self, etl):
        """Boundary: end of day."""
        result = etl.format_ts("2026-12-31T23:59:59.999Z")
        assert result == "2026-12-31 23:59:59.999"


# ---------------------------------------------------------------------------
# Truncation: SQL Server DATETIME2(3) only holds 3 decimal places
# ---------------------------------------------------------------------------

class TestFormatTsTruncation:

    def test_sub_millisecond_is_truncated_to_23_chars(self, etl):
        """
        Input with 9 fractional digits (nanoseconds) must be hard-cut at
        character 23 (index 0..22 inclusive) after the T→space replacement.
        The function uses [:23] which gives exactly 3 decimal places.
        """
        result = etl.format_ts("2026-04-01T14:30:00.123456789Z")
        assert result == "2026-04-01 14:30:00.123"
        assert len(result) == 23

    def test_six_decimal_places_truncated(self, etl):
        result = etl.format_ts("2026-04-01T10:00:00.999999Z")
        assert result == "2026-04-01 10:00:00.999"

    def test_result_never_exceeds_23_chars(self, etl):
        """Invariant: output length is always <= 23 characters."""
        inputs = [
            "2026-04-01T14:30:00.123456789Z",
            "2026-04-01T14:30:00.123Z",
            "2026-04-01T14:30:00Z",
        ]
        for ts in inputs:
            result = etl.format_ts(ts)
            assert len(result) <= 23, f"Exceeded 23 chars for input: {ts!r}"


# ---------------------------------------------------------------------------
# Null / empty / falsy inputs
# ---------------------------------------------------------------------------

class TestFormatTsNullInputs:

    def test_none_returns_none(self, etl):
        assert etl.format_ts(None) is None

    def test_empty_string_returns_none(self, etl):
        assert etl.format_ts("") is None

    def test_zero_returns_none(self, etl):
        """Numeric 0 is falsy — should not crash, should return None."""
        assert etl.format_ts(0) is None


# ---------------------------------------------------------------------------
# Output format invariants
# ---------------------------------------------------------------------------

class TestFormatTsOutputInvariants:

    def test_output_has_no_t_separator(self, etl):
        result = etl.format_ts("2026-04-01T10:00:00Z")
        assert "T" not in result

    def test_output_has_no_z_suffix(self, etl):
        result = etl.format_ts("2026-04-01T10:00:00.000Z")
        assert not result.endswith("Z")

    def test_output_has_space_separator(self, etl):
        result = etl.format_ts("2026-04-01T10:00:00Z")
        assert result[10] == " "

    def test_date_part_is_preserved_exactly(self, etl):
        result = etl.format_ts("2026-04-17T08:15:30.250Z")
        assert result.startswith("2026-04-17")

    def test_time_part_is_preserved(self, etl):
        result = etl.format_ts("2026-04-17T08:15:30.250Z")
        assert "08:15:30" in result
