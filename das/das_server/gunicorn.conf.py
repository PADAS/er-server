from das_server import tracing


def post_fork(server, worker):
    """Set up tracing that export spans to Opentelemetry collector"""
    tracing.config.setup_exporter()
    tracing.config.instrument_app()
