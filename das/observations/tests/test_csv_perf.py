"""Diagnostic: capture queries and timing for the observations CSV export.

Run explicitly with::

    pytest -m perf das/observations/tests/test_csv_perf.py -s

The ``-s`` flag is required to see the logged query/time breakdown.

The test exists to (a) document the current query pattern in
``TrackingDataCsvView`` and (b) guard against N+1 regressions in the
per-subject observation export loop.
"""

from __future__ import annotations

import logging
import re
import time
from collections import Counter
from typing import TYPE_CHECKING

import pytest
from dateutil.relativedelta import relativedelta
from psycopg2.extras import DateTimeTZRange

from django.contrib.gis.geos import Point
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from factories import SourceFactory, SubjectFactory, SubjectSourceFactory
from observations.models import Observation
from observations.views import TrackingDataCsvView, TrackingMetaDataExportView
from utils.csv_streaming import read_streaming_response_content

if TYPE_CHECKING:
    from rest_framework.request import Request
    from rest_framework.response import Response
    from rest_framework.test import APIRequestFactory

    from accounts.models import User

logger = logging.getLogger(__name__)

N_SUBJECTS = 10
N_OBS_PER_SUBJECT = 50


@pytest.fixture
def export_dataset(das_tenant) -> None:
    """Create N_SUBJECTS subjects, each with one source and N_OBS_PER_SUBJECT observations.

    The source's ``assigned_range`` is set to a wide window so all observations fall
    inside it (the export joins through SubjectSource.assigned_range__contains=recorded_at).
    """
    now = timezone.now()
    assigned_range = DateTimeTZRange(lower=now - relativedelta(years=10), upper=now + relativedelta(years=1))

    observations = []
    for i in range(N_SUBJECTS):
        subject = SubjectFactory(name=f"perf-subject-{i}")
        source = SourceFactory(manufacturer_id=f"perf-source-{i}")
        SubjectSourceFactory(subject=subject, source=source, assigned_range=assigned_range)

        for j in range(N_OBS_PER_SUBJECT):
            observations.append(
                Observation(
                    source=source,
                    recorded_at=now - relativedelta(hours=j),
                    location=Point(-103.0 + j * 0.001, 20.0 + j * 0.001),
                    additional={"temp": 20 + j, "voltage": 4.0, "activity": "moving"},
                )
            )
    Observation.objects.bulk_create(observations)


def _table(sql: str) -> str:
    # Only captures the first table after FROM; multi-join queries will show the primary table only.
    m = re.search(r'FROM\s+"?(\w+)"?', sql, re.IGNORECASE)
    return m.group(1) if m else sql[:60]


def _print_query_summary(label: str, queries: list[dict[str, str]], elapsed_s: float) -> None:
    tally: Counter[str] = Counter()
    for q in queries:
        tally[_table(q["sql"])] += 1
    # print() is intentionally avoided; use `pytest -s` to see logging output.
    logger.info("\n=== %s ===", label)
    logger.info("  total queries : %d", len(queries))
    logger.info("  elapsed       : %.1f ms", elapsed_s * 1000)
    logger.info("  by table      :")
    for table, count in tally.most_common():
        logger.info("    %4dx  %s", count, table)


@pytest.mark.perf
@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch", "export_dataset")
class TestObservationsExportPerf:
    def _make_request(self, factory: APIRequestFactory, superuser: User, path: str) -> Request:
        from rest_framework.test import force_authenticate

        request = factory.get(path)
        force_authenticate(request, user=superuser)
        request.user = superuser
        return request

    def _drain(self, response: Response) -> str:
        """Iterate the streaming response so DB queries actually fire."""
        return read_streaming_response_content(response)

    def test_tracking_data_csv_export(self, superuser: User) -> None:
        from rest_framework.test import APIRequestFactory

        factory = APIRequestFactory()
        request = self._make_request(factory, superuser, "/api/v1.0/trackingdata/export/")

        with CaptureQueriesContext(connection) as ctx:
            t0 = time.perf_counter()
            response = TrackingDataCsvView.as_view()(request)
            body = self._drain(response)
            elapsed = time.perf_counter() - t0

        _print_query_summary(
            f"TrackingDataCsvView ({N_SUBJECTS} subjects x {N_OBS_PER_SUBJECT} obs)", ctx.captured_queries, elapsed
        )

        assert response.status_code == 200
        rows = body.split("\r\n")
        # 1 header + N_SUBJECTS * N_OBS_PER_SUBJECT data rows + trailing empty line
        data_rows = [r for r in rows[1:] if r]
        assert (
            len(data_rows) == N_SUBJECTS * N_OBS_PER_SUBJECT
        ), f"expected {N_SUBJECTS * N_OBS_PER_SUBJECT} rows, got {len(data_rows)}"

        # Guard against N+1 regressions: without select_related("subject_subtype__subject_type"),
        # is_stationary_subject fires 2 extra queries per subject. A ceiling of 3*N_SUBJECTS
        # catches severe regressions while tolerating modest fixed overhead.
        assert len(ctx.captured_queries) < 3 * N_SUBJECTS, (
            f"Possible N+1: {len(ctx.captured_queries)} queries for {N_SUBJECTS} subjects — "
            'check select_related("subject_subtype__subject_type") on get_queryset()'
        )

    def test_tracking_metadata_export(self, superuser: User) -> None:
        # TrackingMetaDataExportView accesses subject_subtype.display but not subject_type,
        # so it does not have the same is_stationary_subject N+1 as TrackingDataCsvView.
        # This test verifies correctness and provides a query-count baseline for that view.
        from rest_framework.test import APIRequestFactory

        factory = APIRequestFactory()
        request = self._make_request(factory, superuser, "/api/v1.0/trackingmetadata/export/")

        with CaptureQueriesContext(connection) as ctx:
            t0 = time.perf_counter()
            response = TrackingMetaDataExportView.as_view()(request)
            body = self._drain(response)
            elapsed = time.perf_counter() - t0

        _print_query_summary(f"TrackingMetaDataExportView ({N_SUBJECTS} subjects)", ctx.captured_queries, elapsed)

        assert response.status_code == 200
        rows = [r for r in body.split("\r\n")[1:] if r]
        assert len(rows) == N_SUBJECTS, f"expected {N_SUBJECTS} rows, got {len(rows)}"
