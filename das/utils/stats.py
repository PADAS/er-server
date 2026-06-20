from __future__ import annotations

import logging
import threading
from collections.abc import Sequence
from typing import Final

from opentelemetry.metrics import (
    CallbackOptions,
    Counter,
    Histogram,
    Meter,
    Observation,
)
from opentelemetry.sdk.metrics import MeterProvider

logger = logging.getLogger(__name__)

# Stackdriver tag length limit (carried over from the statsd implementation).
MAX_TAG_LENGTH: Final[int] = 1000

# Default histogram bucket boundaries (advisory) applied when a caller does not
# pass explicit ``buckets``. The OTel SDK default boundaries are millisecond-
# scale (0, 5, 10, 25, ..., 10000), which collapses every seconds-unit metric
# (db_query_time, task.queue_wait, *.lag_seconds) into the bottom buckets and
# makes PromQL percentiles useless. The wrapper can't know a metric's units,
# but seconds is the dominant unit at existing call sites, so these Prometheus-
# client-style boundaries cover both sub-second and second-scale durations and
# still resolve sub-10ms values for the rare ms-unit metric.
DEFAULT_HISTOGRAM_BUCKETS: Final[tuple[float, ...]] = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
    25.0,
    60.0,
    120.0,
    300.0,
    600.0,
)

# Module-level state — set by ``initialize()`` during Django app startup.
# Until then ``_meter`` is ``None`` and all public calls are silent no-ops,
# which avoids binding instruments to the global no-op provider.
_meter: Meter | None = None
_enabled: bool = True

# Instrument caches — OTel instruments are created once per metric name.
# The lock guards the check-then-set pattern in ``increment``/``histogram``
# so two threads cannot both call ``_meter.create_counter`` for the same name.
_instrument_lock = threading.Lock()
_counters: dict[str, Counter] = {}
_histograms: dict[str, Histogram] = {}

# Gauge state: stores the last absolute value per (metric, frozen-attributes)
# key.  An ObservableGauge callback reads from this dict each collection
# cycle, so the exporter always sees the most recent value — exactly like
# statsd gauge semantics.
_gauge_lock = threading.Lock()
_gauge_values: dict[str, dict[tuple[tuple[str, str], ...], float]] = {}
_gauge_instruments: set[str] = set()


# ---------------------------------------------------------------------------
# Lifecycle helpers (called from das_server.otel_metrics)
# ---------------------------------------------------------------------------


def initialize(provider: MeterProvider) -> None:
    """Replace the module meter with one obtained from *provider*."""
    global _meter, _enabled

    if not isinstance(provider, MeterProvider):
        raise TypeError(f"provider must be a MeterProvider, got {type(provider).__name__}")
    _meter = provider.get_meter("das.stats")
    _enabled = True
    with _instrument_lock:
        _counters.clear()
        _histograms.clear()
    with _gauge_lock:
        _gauge_values.clear()
        _gauge_instruments.clear()


def disable() -> None:
    """Disable all metrics collection (no-op mode)."""
    global _enabled
    _enabled = False


# ---------------------------------------------------------------------------
# Tag / attribute helpers
# ---------------------------------------------------------------------------


def _parse_tags(tags: list[str] | dict[str, str] | None) -> dict[str, str]:
    """Convert tags to OTel attributes.

    Two input shapes are accepted:

    - A list of Datadog-style ``["key:value", ...]`` strings. Tags without a
      colon are kept as ``{"tag": "true"}``.
    - A ``{key: value}`` dict, whose items are used directly as attributes.

    For both shapes: keys/values are coerced to ``str``, empty keys are
    skipped, values are truncated to *MAX_TAG_LENGTH*, and empty values map to
    ``"true"``. Empty / ``None`` input yields an empty dict.
    """
    if not tags:
        return {}
    attrs: dict[str, str] = {}
    if isinstance(tags, dict):
        for raw_key, raw_value in tags.items():
            key = str(raw_key)
            if not key:
                continue
            value = str(raw_value)[:MAX_TAG_LENGTH]
            attrs[key] = value if value else "true"
        return attrs
    for tag in tags:
        if not tag:
            continue
        tag = tag[:MAX_TAG_LENGTH]
        key, _, value = tag.partition(":")
        if not key:
            continue
        attrs[key] = value if value else "true"
    return attrs


def _freeze_attrs(attrs: dict[str, str]) -> tuple[tuple[str, str], ...]:
    return tuple(sorted(attrs.items()))


# ---------------------------------------------------------------------------
# Observable gauge helpers
# ---------------------------------------------------------------------------


def _make_gauge_callback(name: str):  # noqa: ANN202
    """Return a callback that yields the last-set value(s) for *name*."""

    def _callback(_options: CallbackOptions) -> list[Observation]:
        with _gauge_lock:
            entries = _gauge_values.get(name, {})
            return [Observation(value=val, attributes=dict(attr_key)) for attr_key, val in entries.items()]

    return _callback


def _ensure_gauge(name: str) -> None:
    """Register an ObservableGauge for *name* if not already registered."""
    if name not in _gauge_instruments:
        _meter.create_observable_gauge(name, callbacks=[_make_gauge_callback(name)])
        _gauge_instruments.add(name)


# ---------------------------------------------------------------------------
# Public API — drop-in replacements for the former datadog wrappers
# ---------------------------------------------------------------------------


def increment(
    metric: str, value: int = 1, tags: list[str] | dict[str, str] | None = None, sample_rate: float = 1
) -> None:
    if not _enabled or _meter is None:
        return
    name = metric.lower()
    counter = _counters.get(name)
    if counter is None:
        with _instrument_lock:
            counter = _counters.get(name)
            if counter is None:
                counter = _meter.create_counter(name)
                _counters[name] = counter
    counter.add(value, attributes=_parse_tags(tags))


def increment_for_view(view_name: str) -> None:
    increment(view_name)


def update_gauge(
    metric: str, value: float, tags: list[str] | dict[str, str] | None = None, sample_rate: float = 1
) -> None:
    """Record an absolute gauge value.

    Uses an ObservableGauge backed by a last-value store so that the
    SDK reads the most recent absolute value at each collection cycle —
    matching statsd gauge semantics exactly.
    """
    if not _enabled or _meter is None:
        return
    name = metric.lower()
    attrs = _parse_tags(tags)
    attr_key = _freeze_attrs(attrs)
    with _gauge_lock:
        _ensure_gauge(name)
        _gauge_values.setdefault(name, {})[attr_key] = value


def histogram(
    metric: str,
    value: float,
    tags: list[str] | dict[str, str] | None = None,
    sample_rate: float | None = None,
    buckets: Sequence[float] | None = None,
) -> None:
    """Record a sample into a histogram.

    *buckets*, if given, sets the explicit bucket-boundary advisory for the
    instrument; otherwise ``DEFAULT_HISTOGRAM_BUCKETS`` is used. Boundaries are
    applied **only at instrument-creation time**: OTel instruments are cached by
    (lowercased) name, so the FIRST call for a given metric name fixes its
    buckets and any differing *buckets* passed on a later call is ignored.

    *sample_rate* is accepted for backward compatibility with the former statsd
    wrapper and is ignored — aggregation is in-process, so client-side sampling
    is unnecessary and counts/samples are exact.
    """
    if not _enabled or _meter is None:
        return
    name = metric.lower()
    hist = _histograms.get(name)
    if hist is None:
        with _instrument_lock:
            hist = _histograms.get(name)
            if hist is None:
                boundaries = buckets if buckets is not None else DEFAULT_HISTOGRAM_BUCKETS
                hist = _meter.create_histogram(name, explicit_bucket_boundaries_advisory=list(boundaries))
                _histograms[name] = hist
    hist.record(value, attributes=_parse_tags(tags))
