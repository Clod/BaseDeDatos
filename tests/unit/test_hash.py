"""
test_hash.py — Phase 1: Unit tests for SentianceETL.get_hash()

WHAT IS BEING TESTED:
    get_hash() produces a SHA-256 hex digest used for deduplication.
    The same raw JSON string must always produce the same hash, and
    any difference in content must produce a different hash.

PROPERTIES VERIFIED:
    - Determinism: same input → same output, always
    - Sensitivity: any character change → different hash
    - Format: output is a 64-character lowercase hex string
    - Whitespace sensitivity: JSON with different spacing is a different hash
      (this is intentional — the ETL hashes the raw string, not parsed JSON)
"""

import hashlib
import pytest


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

class TestGetHashDeterminism:

    def test_same_input_same_hash(self, etl):
        payload = '{"transportEvent": {"id": "abc123"}, "safetyScores": {"overallScore": 0.8}}'
        assert etl.get_hash(payload) == etl.get_hash(payload)

    def test_multiple_calls_are_identical(self, etl):
        payload = '{"foo": "bar"}'
        hashes = [etl.get_hash(payload) for _ in range(10)]
        assert len(set(hashes)) == 1, "get_hash must be deterministic across multiple calls"

    def test_matches_reference_sha256(self, etl):
        """Cross-check against stdlib hashlib to ensure the algorithm is SHA-256."""
        payload = "sentiance-test-payload"
        expected = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        assert etl.get_hash(payload) == expected


# ---------------------------------------------------------------------------
# Sensitivity: different content → different hash
# ---------------------------------------------------------------------------

class TestGetHashSensitivity:

    def test_different_content_different_hash(self, etl):
        assert etl.get_hash('{"a": 1}') != etl.get_hash('{"a": 2}')

    def test_single_char_change_produces_different_hash(self, etl):
        base = '{"overallScore": 0.797}'
        changed = '{"overallScore": 0.798}'
        assert etl.get_hash(base) != etl.get_hash(changed)

    def test_key_order_change_produces_different_hash(self, etl):
        """Raw string hashing is order-sensitive (intentional by design)."""
        a = '{"a": 1, "b": 2}'
        b = '{"b": 2, "a": 1}'
        assert etl.get_hash(a) != etl.get_hash(b)

    def test_whitespace_difference_produces_different_hash(self, etl):
        """Compact vs pretty-printed JSON must hash differently."""
        compact = '{"a":1}'
        pretty = '{"a": 1}'
        assert etl.get_hash(compact) != etl.get_hash(pretty)

    def test_empty_string_has_known_sha256(self, etl):
        """SHA-256 of empty string is a well-known constant."""
        known_sha256_of_empty = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        assert etl.get_hash("") == known_sha256_of_empty


# ---------------------------------------------------------------------------
# Output format
# ---------------------------------------------------------------------------

class TestGetHashOutputFormat:

    def test_output_is_string(self, etl):
        assert isinstance(etl.get_hash("payload"), str)

    def test_output_is_64_chars(self, etl):
        """SHA-256 produces 256 bits = 32 bytes = 64 hex characters."""
        assert len(etl.get_hash("any payload")) == 64

    def test_output_is_lowercase_hex(self, etl):
        result = etl.get_hash("test payload")
        assert result == result.lower(), "Hash must be lowercase"
        assert all(c in "0123456789abcdef" for c in result), "Hash must be hexadecimal"

    def test_hash_fits_in_varchar64_column(self, etl):
        """SdkSourceEvent.payload_hash is VARCHAR(64) — hash must fit."""
        result = etl.get_hash('{"large": "' + "x" * 10000 + '"}')
        assert len(result) <= 64
