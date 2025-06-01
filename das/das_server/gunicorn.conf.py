from das_server import tracing
from das_server.log import init_logging


def post_fork(server, worker):
    """Set up tracing that export spans to Opentelemetry collector"""
    tracing.config.setup_exporter()
    tracing.config.instrument_app()
    # Initialize logging after fork
    init_logging()
