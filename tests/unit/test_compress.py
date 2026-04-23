"""
test_compress.py — Phase 1: Unit tests for SentianceETL.compress_data()

WHAT IS BEING TESTED:
    compress_data() serialises a Python object to JSON and GZIP-compresses
    the result for storage in VARBINARY(MAX) columns (waypoints_json,
    transport_tags_json, preceding_locations_json).

PROPERTIES VERIFIED:
    - Output is bytes (compatible with pyodbc VARBINARY binding)
    - Content round-trips: decompress → JSON parse → equals original
    - Compression actually reduces size for large payloads
    - Falsy inputs (None, [], {}) all return None (SQL NULL)
    - Dict inputs are handled identically to list inputs
"""

import gzip
import json
import pytest


# ---------------------------------------------------------------------------
# Round-trip correctness
# ---------------------------------------------------------------------------

class TestCompressDataRoundTrip:

    def test_list_of_waypoints_round_trips(self, etl):
        """Core use-case: waypoints list compresses and decompresses cleanly."""
        waypoints = [
            {"latitude": -34.55437, "longitude": -58.48303, "speedInMps": 0.0, "timestamp": 1772404523454},
            {"latitude": -34.55438, "longitude": -58.48304, "speedInMps": 5.2, "timestamp": 1772404529361},
        ]
        compressed = etl.compress_data(waypoints)
        decompressed = json.loads(gzip.decompress(compressed))
        assert decompressed == waypoints

    def test_dict_input_round_trips(self, etl):
        """transport_tags_json is a dict, not a list."""
        tags = {"tag1": "value1", "nested": {"a": 1}}
        compressed = etl.compress_data(tags)
        decompressed = json.loads(gzip.decompress(compressed))
        assert decompressed == tags

    def test_single_element_list_round_trips(self, etl):
        data = [{"lat": 0.0, "lng": 0.0}]
        assert json.loads(gzip.decompress(etl.compress_data(data))) == data

    def test_unicode_strings_round_trip(self, etl):
        """Ensure UTF-8 encoding is used for non-ASCII content."""
        data = {"message": "Ñoño 日本語 émoji 🚗"}
        compressed = etl.compress_data(data)
        decompressed = json.loads(gzip.decompress(compressed).decode("utf-8"))
        assert decompressed == data

    def test_large_waypoints_list_round_trips(self, etl):
        """Simulate a real trip with 100 waypoints."""
        waypoints = [
            {"latitude": -34.55 + i * 0.001, "longitude": -58.48 + i * 0.001, "timestamp": 1000000 + i}
            for i in range(100)
        ]
        compressed = etl.compress_data(waypoints)
        decompressed = json.loads(gzip.decompress(compressed))
        assert decompressed == waypoints


# ---------------------------------------------------------------------------
# Output type
# ---------------------------------------------------------------------------

class TestCompressDataOutputType:

    def test_output_is_bytes(self, etl):
        result = etl.compress_data([{"lat": 1.0}])
        assert isinstance(result, bytes)

    def test_output_is_valid_gzip(self, etl):
        """gzip.decompress must not raise."""
        result = etl.compress_data({"key": "value"})
        gzip.decompress(result)  # Should not raise


# ---------------------------------------------------------------------------
# Compression efficiency
# ---------------------------------------------------------------------------

class TestCompressDataEfficiency:

    def test_compression_reduces_size_for_large_payload(self, etl):
        """GZIP should achieve meaningful compression on repetitive JSON."""
        large_payload = [{"latitude": -34.55437, "longitude": -58.48303, "speedInMps": 0.0}] * 200
        raw_size = len(json.dumps(large_payload).encode("utf-8"))
        compressed_size = len(etl.compress_data(large_payload))
        assert compressed_size < raw_size, (
            f"Expected compression: raw={raw_size} bytes, compressed={compressed_size} bytes"
        )


# ---------------------------------------------------------------------------
# Falsy / null inputs → SQL NULL
# ---------------------------------------------------------------------------

class TestCompressDataNullInputs:

    def test_none_returns_none(self, etl):
        assert etl.compress_data(None) is None

    def test_empty_list_returns_none(self, etl):
        """Empty list is falsy → should return None (SQL NULL)."""
        assert etl.compress_data([]) is None

    def test_empty_dict_returns_none(self, etl):
        """Empty dict is falsy → should return None (SQL NULL)."""
        assert etl.compress_data({}) is None

    def test_zero_returns_none(self, etl):
        """Numeric 0 is falsy."""
        assert etl.compress_data(0) is None

    def test_false_returns_none(self, etl):
        assert etl.compress_data(False) is None
