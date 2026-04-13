"""
Speed and reliability tests for the observation segment vector tile endpoint.

Run with: pytest -m perf
Excluded from default test run so CI stays fast; run in a dedicated job or locally
when validating tile response time and correctness.

Threshold: set VECTOR_TILE_PERF_THRESHOLD_MS (milliseconds) to enforce a max
response time; if unset or 0, only status and Content-Type are asserted.
"""

# Register fixtures from test_vector_tiles so they are available when running
# only this module (e.g. pytest -m perf).
pytest_plugins = ["observations.tests.test_vector_tiles"]

import logging
import os
import time

import pytest

from django.urls import reverse
from rest_framework.test import APIRequestFactory

from observations.views.vector_tiles_segments import ObservationSegmentTileView

logger = logging.getLogger(__name__)

# Fixed tile coordinates (z, x, y) covering a few zoom levels. Valid for web mercator:
# z in [0, 24], x/y in [0, 2^z - 1].
TILE_SAMPLES = [
    (10, 512, 512),
    (12, 100, 200),
    (14, 500, 500),
]


def _get_perf_threshold_ms():
    """Return max allowed response time in ms; 0 means do not assert latency."""
    try:
        return int(os.environ.get("VECTOR_TILE_PERF_THRESHOLD_MS", "0"))
    except ValueError:
        return 0


@pytest.mark.diag
@pytest.mark.django_db
class TestObservationSegmentTilePerformance:
    """Performance and reliability checks for observation segment vector tiles.

    Uses the same request path as TestConsolidatedVectorTiles (direct view call
    with request.user set) to avoid session/auth variability. Requires
    tile_test_subject_visible so the tile view has valid segment data to render.
    """

    def _tile_response(self, user, patch_vector_tile_tenant, z, x, y):
        """Return (response, elapsed_seconds) for the given tile."""
        url = reverse("observation-segments-vector-tiles", kwargs={"z": z, "x": x, "y": y})
        request = APIRequestFactory().get(url)
        request.user = user
        view = ObservationSegmentTileView.as_view()
        start = time.perf_counter()
        response = view(request, z, x, y)
        elapsed = time.perf_counter() - start
        return response, elapsed

    def test_tile_returns_200_and_mvt(
        self,
        das_tenant_monkeypatch,
        tenant_settings,
        tile_test_subject_visible,
        user_with_realtime_access,
        patch_vector_tile_tenant,
    ):
        """Each sampled tile returns 200/204 and correct Content-Type."""
        for z, x, y in TILE_SAMPLES:
            response, _ = self._tile_response(user_with_realtime_access, patch_vector_tile_tenant, z, x, y)
            assert response.status_code in (200, 204), f"tile {z}/{x}/{y} returned {response.status_code}"
            assert response.get("Content-Type", "").startswith(
                "application/vnd.mapbox-vector-tile"
            ), f"tile {z}/{x}/{y} wrong Content-Type: {response.get('Content-Type')}"

    def test_tile_response_time_below_threshold(
        self,
        das_tenant_monkeypatch,
        tenant_settings,
        tile_test_subject_visible,
        user_with_realtime_access,
        patch_vector_tile_tenant,
    ):
        """If VECTOR_TILE_PERF_THRESHOLD_MS is set, each tile responds within that time."""
        threshold_ms = _get_perf_threshold_ms()
        if threshold_ms <= 0:
            pytest.skip("VECTOR_TILE_PERF_THRESHOLD_MS not set or 0; skipping latency assertion")
        threshold_sec = threshold_ms / 1000.0
        for z, x, y in TILE_SAMPLES:
            response, elapsed = self._tile_response(user_with_realtime_access, patch_vector_tile_tenant, z, x, y)
            assert response.status_code in (200, 204), f"tile {z}/{x}/{y} returned {response.status_code}"
            assert elapsed < threshold_sec, f"tile {z}/{x}/{y} took {elapsed:.3f}s (threshold {threshold_sec}s)"
            logger.info("tile %s/%s/%s: %d ms", z, x, y, int(elapsed * 1000))
