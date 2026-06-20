from das_server import tracing
from das_server.log import init_logging
from das_server.otel_metrics import configure_metrics


def post_fork(server, worker):
    """Set up per-worker tracing, logging, and metrics after fork.

    Spans are exported directly to Cloud Trace via ``CloudTraceSpanExporter``
    (there is no OpenTelemetry collector in this path).
    """
    tracing.config.setup_exporter()
    tracing.config.instrument_app()
    # Initialize logging after fork
    init_logging()
    # Initialize metrics after fork — the periodic exporter thread must be
    # spawned per-worker, not inherited from the gunicorn master.
    configure_metrics()
