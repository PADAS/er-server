from opentelemetry import trace
from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
from opentelemetry.instrumentation.django import DjangoInstrumentor
from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Span

from django.conf import settings
from django.http.request import HttpRequest


def request_hook(span: Span, request: HttpRequest):
    if request.path == "/api/v1.0/status":
        span.set_attribute("tracing.excluded", True)
        return
    span.update_name(request.path)


class OpenTelemetryConfiguration:
    tracing_enabled: bool = settings.TRACING_ENABLED
    tracer_provider_configured: bool = False

    def setup_tracer_provider(self):
        app_name = settings.SERVICE_NAME
        if self.tracing_enabled:
            resource = Resource.create(attributes={SERVICE_NAME: app_name})

            tracer_provider = TracerProvider(resource=resource)

            trace.set_tracer_provider(tracer_provider)

            self.tracer_provider_configured = True

    def setup_exporter(self):
        if self.tracing_enabled:
            if not self.tracer_provider_configured:
                self.setup_tracer_provider()

            trace.get_tracer_provider().add_span_processor(BatchSpanProcessor(CloudTraceSpanExporter()))

    def instrument_app(self):
        if self.tracing_enabled:
            DjangoInstrumentor().instrument(request_hook=request_hook, is_sql_commentor_enabled=True)
            Psycopg2Instrumentor().instrument(enable_commenter=True)
            RedisInstrumentor().instrument()
            RequestsInstrumentor().instrument()


config = OpenTelemetryConfiguration()
