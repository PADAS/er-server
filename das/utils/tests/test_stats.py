from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import utils.stats as stats
from utils.stats import DEFAULT_HISTOGRAM_BUCKETS, MAX_TAG_LENGTH, _parse_tags


class TestParseTags:
    def test_returns_empty_dict_for_none(self):
        assert _parse_tags(None) == {}

    def test_returns_empty_dict_for_empty_list(self):
        assert _parse_tags([]) == {}

    def test_returns_empty_dict_for_empty_dict(self):
        assert _parse_tags({}) == {}

    def test_parses_list_key_value_strings(self):
        assert _parse_tags(["type:gps", "provider:savannah"]) == {"type": "gps", "provider": "savannah"}

    def test_list_tag_without_colon_maps_to_true(self):
        assert _parse_tags(["enabled"]) == {"enabled": "true"}

    def test_list_skips_empty_tags(self):
        assert _parse_tags(["", "type:gps"]) == {"type": "gps"}

    def test_dict_values_preserved(self):
        assert _parse_tags({"type": "gps", "provider": "savannah"}) == {"type": "gps", "provider": "savannah"}

    def test_dict_empty_value_maps_to_true(self):
        assert _parse_tags({"type": ""}) == {"type": "true"}

    def test_dict_skips_empty_key(self):
        assert _parse_tags({"": "value", "type": "gps"}) == {"type": "gps"}

    def test_dict_coerces_non_string_key_and_value(self):
        assert _parse_tags({1: 2}) == {"1": "2"}

    def test_dict_truncates_value_to_max_tag_length(self):
        long_value = "x" * (MAX_TAG_LENGTH + 50)
        result = _parse_tags({"key": long_value})
        assert result["key"] == "x" * MAX_TAG_LENGTH

    def test_list_truncates_to_max_tag_length(self):
        long_value = "v" * (MAX_TAG_LENGTH + 50)
        result = _parse_tags([f"key:{long_value}"])
        # The whole "key:<value>" string is truncated to MAX_TAG_LENGTH.
        assert len(f"key:{result['key']}") == MAX_TAG_LENGTH

    def test_list_skips_empty_key_colon_value(self):
        # ":value" partitions into key="" which must be skipped.
        assert _parse_tags([":value"]) == {}

    def test_list_skips_bare_colon(self):
        # ":" partitions into key="" and value="" — both empty, must be skipped.
        assert _parse_tags([":"]) == {}

    def test_list_skips_empty_key_but_keeps_valid_tags(self):
        # Empty-key tag is skipped; valid tag is still included.
        assert _parse_tags([":orphan", "env:prod"]) == {"env": "prod"}


class TestPublicApiAcceptsDictTags:
    @pytest.fixture(autouse=True)
    def fake_meter(self, monkeypatch: pytest.MonkeyPatch):
        meter = MagicMock()
        monkeypatch.setattr(stats, "_meter", meter)
        monkeypatch.setattr(stats, "_enabled", True)
        monkeypatch.setattr(stats, "_counters", {})
        monkeypatch.setattr(stats, "_histograms", {})
        monkeypatch.setattr(stats, "_gauge_values", {})
        monkeypatch.setattr(stats, "_gauge_instruments", set())
        return meter

    def test_increment_with_dict_tags(self, fake_meter: MagicMock):
        counter = fake_meter.create_counter.return_value
        stats.increment("sensor", tags={"type": "gps", "provider": "savannah"})
        counter.add.assert_called_once_with(1, attributes={"type": "gps", "provider": "savannah"})

    def test_histogram_with_dict_tags(self, fake_meter: MagicMock):
        hist = fake_meter.create_histogram.return_value
        stats.histogram("latency", 12.5, tags={"endpoint": "ingest"})
        hist.record.assert_called_once_with(12.5, attributes={"endpoint": "ingest"})

    def test_update_gauge_with_dict_tags(self, fake_meter: MagicMock):
        stats.update_gauge("queue_depth", 7.0, tags={"queue": "default"})
        stored = stats._gauge_values["queue_depth"]
        assert dict(next(iter(stored.keys()))) == {"queue": "default"}
        assert next(iter(stored.values())) == 7.0


class TestHistogramBuckets:
    @pytest.fixture(autouse=True)
    def fake_meter(self, monkeypatch: pytest.MonkeyPatch):
        meter = MagicMock()
        monkeypatch.setattr(stats, "_meter", meter)
        monkeypatch.setattr(stats, "_enabled", True)
        monkeypatch.setattr(stats, "_histograms", {})
        return meter

    def test_default_boundaries_advisory_passed_on_creation(self, fake_meter: MagicMock):
        stats.histogram("db_query_time", 0.42)
        fake_meter.create_histogram.assert_called_once_with(
            "db_query_time", explicit_bucket_boundaries_advisory=list(DEFAULT_HISTOGRAM_BUCKETS)
        )

    def test_per_call_buckets_override_default(self, fake_meter: MagicMock):
        stats.histogram("segment.duration_ms", 12.0, buckets=[1, 10, 100])
        fake_meter.create_histogram.assert_called_once_with(
            "segment.duration_ms", explicit_bucket_boundaries_advisory=[1, 10, 100]
        )

    def test_instrument_cached_by_name_first_buckets_win(self, fake_meter: MagicMock):
        stats.histogram("latency", 1.0, buckets=[1, 2, 3])
        stats.histogram("latency", 2.0, buckets=[100, 200, 300])
        # Only the first call creates the instrument; the second reuses it.
        fake_meter.create_histogram.assert_called_once_with("latency", explicit_bucket_boundaries_advisory=[1, 2, 3])
        hist = fake_meter.create_histogram.return_value
        assert hist.record.call_count == 2

    def test_sample_rate_is_ignored(self, fake_meter: MagicMock):
        hist = fake_meter.create_histogram.return_value
        stats.histogram("latency", 5.0, sample_rate=0.1)
        hist.record.assert_called_once_with(5.0, attributes={})


class TestInitialize:
    def test_raises_type_error_on_non_meter_provider(self):
        with pytest.raises(TypeError) as exc_info:
            stats.initialize(object())
        assert "MeterProvider" in str(exc_info.value)
        assert "object" in str(exc_info.value)

    def test_accepts_real_meter_provider(self):
        from opentelemetry.sdk.metrics import MeterProvider

        provider = MeterProvider()
        try:
            stats.initialize(provider)
            assert stats._meter is not None
            assert stats._enabled is True
        finally:
            provider.shutdown()
            stats.disable()
