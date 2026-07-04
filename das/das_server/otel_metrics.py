from __future__ import annotations

import logging
import os
import urllib.error
import urllib.request
from typing import Any, Callable, Final

import google.auth
import google.auth.exceptions
import google.auth.transport.requests
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import SERVICE_NAME, Resource

from django.conf import settings

import utils.stats as stats_module

logger = logging.getLogger(__name__)

GCP_TELEMETRY_ENDPOINT = "https://telemetry.googleapis.com/v1/metrics"
# The GCP Telemetry API rejects any export request with more than 200 data
# points ("A maximum of 200 points can be written in a single request"), so
# exports must be split into batches of at most this size.
GCP_MAX_POINTS_PER_REQUEST: Final[int] = 200
_MONITORING_SCOPES = ["https://www.googleapis.com/auth/monitoring.write"]

# Per-pod auto-detection sources. These let GKE deployments produce
# correctly-labeled metrics without plumbing CLUSTER_* env vars through
# the configmap.
_METADATA_BASE_URL = "http://metadata.google.internal/computeMetadata/v1/instance/attributes"
_METADATA_TIMEOUT_S = 2.0
_K8S_NAMESPACE_FILE = "/var/run/secrets/kubernetes.io/serviceaccount/namespace"

# Values the operator may have left at their settings.py defaults — they
# all mean "not set" for the purpose of auto-detection.
_PLACEHOLDER_VALUES = {"", "UNSET", "global"}


def _read_gce_metadata_attribute(name: str) -> str | None:
    """Read a single GCE-instance metadata attribute (e.g. ``cluster-location``).

    Returns ``None`` outside of GCE/GKE (metadata server unreachable) or when
    the attribute isn't present.
    """
    try:
        req = urllib.request.Request(
            f"{_METADATA_BASE_URL}/{name}",
            headers={"Metadata-Flavor": "Google"},
        )
        with urllib.request.urlopen(req, timeout=_METADATA_TIMEOUT_S) as resp:
            value = resp.read().decode("utf-8").strip()
            return value or None
    except (urllib.error.URLError, TimeoutError, OSError):
        return None


def _read_pod_namespace() -> str | None:
    """Read the pod's namespace from the kubelet-mounted serviceaccount file."""
    try:
        with open(_K8S_NAMESPACE_FILE, "r", encoding="utf-8") as fp:
            value = fp.read().strip()
            return value or None
    except OSError:
        return None


def _resolve(setting_value: str, detector: Callable[[], str | None], label: str) -> str:
    """Return *setting_value* if set, else fall back to *detector*'s result.

    Logs at INFO level when a detector successfully fills in a value, so
    operators can see where each resource attribute came from.
    """
    if setting_value not in _PLACEHOLDER_VALUES:
        return setting_value
    detected = detector()
    if detected:
        logger.info("Auto-detected %s: %s", label, detected)
        return detected
    return setting_value


class GCPOTLPMetricExporter(OTLPMetricExporter):
    """OTLP HTTP metric exporter that authenticates with GCP ADC.

    Uses a ``google.auth.transport.requests.AuthorizedSession`` so the bearer
    token is refreshed per request through google-auth's public API — short-
    lived tokens (workload identity, metadata server) work without manual
    rotation, and we never touch the parent exporter's private internals.
    """

    def __init__(self, credentials: Any, project: str | None = None, **kwargs: Any) -> None:
        resolved_project = project or settings.GCP_PROJECT_ID or None
        auth_session = google.auth.transport.requests.AuthorizedSession(credentials)
        if resolved_project:
            auth_session.headers["x-goog-user-project"] = resolved_project
        # Hold our own reference so the diagnostic override below can read the
        # session headers without reaching into the parent's private state.
        self._auth_session = auth_session
        self._project = resolved_project
        logger.info(
            "GCP OTLP exporter credentials resolved: project=%r credential_type=%s",
            resolved_project,
            type(credentials).__name__,
        )
        kwargs.setdefault("endpoint", GCP_TELEMETRY_ENDPOINT)
        # Split exports into batches so we never exceed the GCP Telemetry
        # API's 200-points-per-request limit (see GCP_MAX_POINTS_PER_REQUEST).
        kwargs.setdefault("max_export_batch_size", GCP_MAX_POINTS_PER_REQUEST)
        super().__init__(session=auth_session, **kwargs)

    def _export(self, *args: Any, **kwargs: Any) -> Any:
        # TEMP DIAGNOSTIC: surface the response body when the GCP Telemetry
        # API returns a non-2xx, so we can see *why* (missing IAM role, wrong
        # quota project, API not enabled, etc.). The upstream OTLP exporter
        # logs only the status code, which is rarely enough to debug 403s.
        # Signature is variadic because the parent method takes a deadline
        # arg in some SDK versions and not in others.
        # Remove (or formally adopt) once metrics are confirmed flowing in
        # production — see docs/architecture/metrics_and_logging.md.
        response = super()._export(*args, **kwargs)
        status = getattr(response, "status_code", None)
        if status is not None and status >= 400:
            body = getattr(response, "text", "")
            logger.warning(
                "OTLP export rejected: status=%s project_header=%r body=%s",
                status,
                self._auth_session.headers.get("x-goog-user-project"),
                body[:2000],
            )
        return response


def configure_metrics() -> MeterProvider | None:
    """Initialise the OTel MeterProvider and wire it into ``utils.stats``.

    Returns the provider (mainly useful for tests) or ``None`` when
    metrics are disabled.
    """
    if settings.DISABLE_STATSD:
        logger.info("Metrics collection is disabled (DISABLE_STATSD=True)")
        stats_module.disable()
        return None

    try:
        adc_credentials, adc_project = google.auth.default(scopes=_MONITORING_SCOPES)
    except google.auth.exceptions.DefaultCredentialsError:
        logger.warning(
            "Metrics collection disabled — no Google Application Default " "Credentials available in this environment"
        )
        stats_module.disable()
        return None

    gcp_project_id = settings.GCP_PROJECT_ID or adc_project or ""
    if not gcp_project_id:
        logger.warning(
            "Metrics collection disabled — could not resolve a GCP project id "
            "(set GOOGLE_CLOUD_PROJECT or GCP_PROJECT_ID in the pod env)"
        )
        stats_module.disable()
        return None

    # Resolve resource labels from settings, falling back to per-pod
    # auto-detection so a vanilla GKE deployment needs no CLUSTER_* env vars.
    cluster_location = _resolve(
        settings.CLUSTER_LOCATION,
        lambda: _read_gce_metadata_attribute("cluster-location"),
        "cluster location",
    )
    cluster_name = _resolve(
        settings.CLUSTER_NAME,
        lambda: _read_gce_metadata_attribute("cluster-name"),
        "cluster name",
    )
    cluster_namespace = _resolve(
        settings.CLUSTER_NAMESPACE,
        _read_pod_namespace,
        "pod namespace",
    )

    if cluster_location in _PLACEHOLDER_VALUES:
        # The GCP Telemetry API rejects exports with a "global" or empty
        # location label, so failing fast here gives a clearer diagnostic
        # than a permanent 400 in the background exporter loop.
        logger.warning(
            "Metrics collection disabled — CLUSTER_LOCATION must be a real GCP "
            "region or zone (e.g. us-central1), got %r",
            settings.CLUSTER_LOCATION,
        )
        stats_module.disable()
        return None

    # Suffix the instance id with the worker PID so each gunicorn / celery
    # worker in the same pod writes to a distinct time series. Without this,
    # Cloud Monitoring rejects the second+ worker's target_info writes
    # (minimum sampling period) because every worker in the pod produces the
    # same (resource, labels) tuple at the same export interval.
    instance_id = f"{settings.POD_NAME}-{os.getpid()}"

    resource = Resource.create(
        attributes={
            SERVICE_NAME: settings.SERVICE_NAME,
            "service.instance.id": instance_id,
            "k8s.cluster.name": cluster_name,
            "k8s.namespace.name": cluster_namespace,
            "k8s.pod.name": settings.POD_NAME,
            "location": cluster_location,
            "gcp.project_id": gcp_project_id,
        },
    )

    exporter = GCPOTLPMetricExporter(credentials=adc_credentials, project=gcp_project_id)

    export_interval_ms = getattr(settings, "METRICS_EXPORT_INTERVAL_MS", 60_000)
    reader = PeriodicExportingMetricReader(
        exporter,
        export_interval_millis=export_interval_ms,
    )

    provider = MeterProvider(resource=resource, metric_readers=[reader])
    stats_module.initialize(provider)

    logger.info(
        "Metrics collection enabled — exporting to %s every %dms",
        GCP_TELEMETRY_ENDPOINT,
        export_interval_ms,
    )
    return provider
