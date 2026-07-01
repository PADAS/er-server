# Metrics and Logging

This document describes how the EarthRanger Django application emits metrics and logs,
how they reach Google Cloud Observability, and what configuration is required in each
environment.

## Metrics

### Overview

The application emits application-level metrics (counters, gauges, histograms) through
a thin wrapper module, `utils.stats`, which is backed by the OpenTelemetry Python SDK.
Metrics are aggregated in-process and exported over OTLP/HTTP directly to Google
Cloud's Telemetry API (`https://telemetry.googleapis.com/v1/metrics`), which ingests
them into **Managed Service for Prometheus**.

Previously metrics were emitted as UDP statsd packets to a `telegraf` sidecar, which
then forwarded them to Cloud Monitoring. The sidecar has been removed; the application
now aggregates and exports metrics itself.

### How metrics appear in Cloud Monitoring

- **Metric type prefix.** `prometheus.googleapis.com/<metric-name>/<kind>` where
  `<kind>` is `counter`, `gauge`, or `histogram`. Periods and slashes in our metric
  names are converted to underscores by the ingest pipeline.
- **MonitoredResource.** `prometheus_target` — a fixed-schema resource with labels
  `location`, `cluster`, `namespace`, `job`, `instance`.
- **Billing.** Sample ingestion is billed under the "Prometheus Samples Ingested"
  SKU, not under custom metrics.
- **Query surface.** PromQL in the Cloud Monitoring UI and Metrics Explorer.

### Resource attributes set by the application

| prometheus_target label | Source OTel attribute | Django setting |
| --- | --- | --- |
| `job` | `service.name` | `SERVICE_NAME` |
| `cluster` | `k8s.cluster.name` | `CLUSTER_NAME` |
| `namespace` | `k8s.namespace.name` | `CLUSTER_NAMESPACE` |
| `location` | `location` | `CLUSTER_LOCATION` |
| `instance` | `service.instance.id` (`f"{POD_NAME}-{os.getpid()}"`) | `POD_NAME` + worker PID |

`location` and `instance` are **required** by the ingest API — points that resolve
to empty values on either are rejected. Note that `service.instance.id` is the pod
name **suffixed with the process PID**, so each worker process within a pod gets a
distinct `instance` value (see "Cardinality and cost"). `CLUSTER_LOCATION` is injected via the
`server-configmap` (cluster-wide constant); `POD_NAME` is injected per-pod using the
Kubernetes Downward API (`fieldRef: metadata.name`) on every Django container spec.

### Call-site API

Application code uses four functions from `utils.stats`:

- `increment(metric, value=1, tags=None)` — increments a monotonic counter.
- `increment_for_view(view_name)` — convenience wrapper around `increment`.
- `update_gauge(metric, value, tags=None)` — records an absolute gauge value.
- `histogram(metric, value, tags=None, buckets=None)` — records a sample into a histogram.

`tags` accepts either a list of "key:value" strings (the colon-delimited tag
convention from statsd/DogStatsD, carried over from the former statsd wrapper — the
application never ran Datadog itself) or a plain `{key: value}` dict. For both shapes,
keys and values are coerced to strings, empty keys are skipped, and an empty value maps
to "true"; a list entry with no colon (e.g. "realtime") is treated the same way
(`{"realtime": "true"}`). List entries are truncated to 1000 characters before parsing;
dict values are truncated to 1000 characters to match the Stackdriver tag length limit.
Tags are translated into OpenTelemetry attributes before being attached to each recorded
data point.

`histogram` accepts an optional `buckets` (a sequence of upper-bound boundaries) that
sets the instrument's explicit bucket-boundary advisory. When omitted, the module
default (`DEFAULT_HISTOGRAM_BUCKETS`, see below) is used. **Caching caveat:** OTel
instruments are created once and cached by (lowercased) metric name, so the *first* call
for a given name fixes its buckets — `buckets` passed on later calls for the same name is
ignored. Choose the boundaries at the first/only call site for each metric.

These functions also accept a `sample_rate` argument for backward compatibility with the
former statsd wrapper, but it is **ignored**: aggregation is now in-process, so
client-side sampling is unnecessary and counts/samples are exact.

All four entry points are silent no-ops until the meter has been initialised by
`configure_metrics()`, so importing `utils.stats` during management commands or tests
does not require a live exporter.

### Histogram buckets

The OTel SDK's default histogram boundaries are millisecond-scale (`0, 5, 10, 25, …,
10000`). Several call sites record **seconds** (`db_query_time`, `task.queue_wait`,
`observation_segment.*.lag_seconds`), so under the SDK default nearly every sample
collapses into the bottom buckets and PromQL percentiles are meaningless.

`utils.stats.DEFAULT_HISTOGRAM_BUCKETS` replaces that default with a Prometheus-client-
style range `(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 25.0, 60.0,
120.0, 300.0, 600.0)`. The wrapper can't know a metric's units, but seconds is the
dominant unit at existing call sites, so this resolves both sub-second and second-scale
durations while still distinguishing sub-10ms values.

To override per metric, pass `buckets=` at the metric's first call site. Metrics that are
not in seconds do this today: `observation_segment.*.duration_ms` (millisecond-scale) and
the count-style `observation_segment.*.batch_size`, `…reconcile.sources_checked`,
`…reconcile.gaps_detected` all pass explicit count-/ms-scale boundaries in
`observations/tasks.py`.

### Startup wiring

`configure_metrics()` is called **after fork** (or, for rt-api, inside the serving
process), never at Django app-ready time, because the `PeriodicExportingMetricReader` it
creates runs a background thread that cannot be safely inherited across `os.fork()`. The
three entry points are:

- `das_server.gunicorn.conf.post_fork` — each gunicorn worker initializes metrics
  immediately after fork.
- `das_server.celery.init_metrics_after_fork` (a `worker_process_init` signal handler)
  — each Celery prefork worker initializes metrics immediately after fork.
- `rt_api.management.commands.rtserver.Command.inner_run` — the rt-api Socket.IO server
  is launched as a Django management command (`async_manage.py rtserver`), not by
  gunicorn or celery, so neither hook above fires. It calls `configure_metrics()` from
  `inner_run` (the method that runs in the actual serving process; with Django's
  autoreloader active this is the child process) before serving traffic. Under
  eventlet's full `monkey_patch()`, the reader's background thread becomes a greenlet,
  which works as expected.

`configure_metrics()`:

1. Returns early (disabling `utils.stats`) if `DISABLE_STATSD` is set.
2. Probes Google Application Default Credentials (ADC). If none are available it logs
   a single warning, disables `utils.stats`, and returns. This ensures image builds,
   test runs, and local developer environments don't spin up a background exporter
   thread that would fail on every collection cycle.
3. Builds a `MeterProvider` with a `Resource` tagged by `service.name`,
   `k8s.cluster.name`, and `k8s.namespace.name`, attaches a
   `PeriodicExportingMetricReader` driving a custom `GCPOTLPMetricExporter`, and hands
   the provider to `utils.stats.initialize()`.

`GCPOTLPMetricExporter` extends the standard OTLP/HTTP metric exporter and authenticates
through google-auth. `configure_metrics()` resolves Application Default Credentials once
(via `google.auth.default(...)`) and passes them into the exporter's constructor. The
exporter wraps those credentials in a `google.auth.transport.requests.AuthorizedSession`
and hands it to the parent OTLP exporter through its public `session=` keyword argument.
google-auth then refreshes the bearer token per request on that session, so short-lived
tokens from workload identity or the metadata server work without any manual rotation —
and we never touch the parent exporter's private internals.[^export-diagnostic]

### Settings

| Setting | Default | Purpose |
| --- | --- | --- |
| `DISABLE_STATSD` | `True` | Master kill-switch. When true, `configure_metrics()` disables all metrics. |
| `SERVICE_NAME` | `"das-api"` | Attached as `service.name` → prometheus_target `job`. |
| `CLUSTER_NAME` | `"UNSET"` | Attached as `k8s.cluster.name` → prometheus_target `cluster`. Auto-detected from the GCE metadata server (`instance/attributes/cluster-name`) when left at the default on GKE. |
| `CLUSTER_NAMESPACE` | `"UNSET"` | Attached as `k8s.namespace.name` → prometheus_target `namespace`. Auto-detected from the kubelet-mounted file `/var/run/secrets/kubernetes.io/serviceaccount/namespace` when left at the default. |
| `CLUSTER_LOCATION` | `"global"` | Attached as `location` → prometheus_target `location` (required by ingest). **Must be a real GCP region or zone (e.g. `us-central1`) in production** — the Telemetry API rejects `"global"` and empty values with a 400. Auto-detected from the GCE metadata server (`instance/attributes/cluster-location`) when left at the default on GKE; `configure_metrics()` fails closed if it still can't be resolved. |
| `POD_NAME` | `socket.gethostname()` | Attached as `service.instance.id` → prometheus_target `instance` (required by ingest). Inside a Kubernetes pod the hostname defaults to the pod name, so the fallback still yields a per-pod value if the downward API isn't wired up. |
| `METRICS_EXPORT_INTERVAL_MS` | `60000` | How often the periodic reader collects and exports. |

`DISABLE_STATSD` defaults to `True`. Production deployments that want metrics
must explicitly set `DISABLE_STATSD=false` in the pod environment (see the
`server-configmap` for the API/worker/rt-api/beat/analyzer/mql deployments).
`CLUSTER_NAME`, `CLUSTER_NAMESPACE`, and `CLUSTER_LOCATION` can be injected
from the same configmap (see
`templated-deployment/templates/circleci-01-server-configmap.yaml` and the
`cluster_location` Terraform variable in `templated-deployment/inputs.tf`),
but on GKE they will also be auto-detected per-pod if left at their defaults
— so omitting them from the configmap is a supported deployment pattern.

`POD_NAME` is injected per-pod via the Kubernetes Downward API:

```yaml
env:
  - name: POD_NAME
    valueFrom:
      fieldRef:
        fieldPath: metadata.name
```

This block is present on every Django container spec under
`templated-deployment/templates/` (api, rt-api, beat, worker, worker-analyzer, mql).
If the downward API isn't wired up, `settings.py` falls back to
`socket.gethostname()` — inside a pod, the container hostname defaults to the
pod name, so metrics still carry a per-pod `instance` label.

### Authentication

The exporter uses Application Default Credentials. On GKE this means the pod must run
under a Kubernetes service account annotated for workload identity to a Google service
account that has the required IAM roles.

The requested OAuth scope is `https://www.googleapis.com/auth/monitoring.write` — the
write-only scope, paired with the least-privilege role listed below.

### IAM permissions

The Google service account used by the workload must have the following role on the
project that receives metrics:

| Role | Permission granted | Needed for |
| --- | --- | --- |
| `roles/monitoring.metricWriter` | `monitoring.timeSeries.create` | Writing metric time series via the Telemetry API. |

`roles/monitoring.metricWriter` is the intended least-privilege role for service
accounts and agents shipping custom metrics; `roles/monitoring.editor` and
`roles/monitoring.admin` also grant the underlying permission but are broader than
this workload needs.

If this pipeline is later extended to emit OTLP traces or logs through the same
telemetry endpoint, the additional roles are:

- **Traces** — `roles/cloudtrace.agent` (`cloudtrace.traces.patch`).
- **Logs** — `roles/logging.logWriter` (`logging.logEntries.create`).

### Behaviour in environments without credentials

- **Docker image build (`collectstatic`)** — ADC probe fails, metrics are disabled for
  the lifetime of the build process. No background thread is started.
- **Unit tests / local development** — same as above. Tests do not need to mock out
  the exporter.
- **CI feature-branch builds** — if ADC is not injected (for example on `ERA-*`
  branches that don't have a Google auth step), the same graceful-disable path applies.
- **Production GKE pod** — ADC is available via workload identity; metrics export
  every `METRICS_EXPORT_INTERVAL_MS` milliseconds.

### Operational notes

- Aggregation happens in-process. Every distinct combination of metric name plus
  attribute values creates a live entry in Python memory. High-cardinality tags (e.g.
  per-request IDs, per-user values) will grow unboundedly — prefer low-cardinality
  dimensions.
- Up to `METRICS_EXPORT_INTERVAL_MS` of data is lost if a process crashes before the
  next export cycle. Lower the interval if freshness matters more than export cost.
- The background exporter runs on a dedicated thread; it does not block request
  handling, but each export cycle does a blocking HTTPS POST with a token refresh.

### Cardinality and cost

Every unique combination of `(metric, cluster, namespace, job, location, instance,
+ user-supplied tags)` is a distinct time series in Managed Prometheus. Because
`service.instance.id` is `f"{POD_NAME}-{os.getpid()}"`, **each process creates its own
series** — every gunicorn worker, every celery prefork child, and the rt-api process
each get a distinct `instance`. The series count is therefore
`pods × processes-per-pod`, not just pods.

This is deliberate: metrics are aggregated in-process and exported as **cumulative**
series, and two processes cannot safely write the same cumulative series (the ingest API
rejects the second+ writer's points for the same `(resource, labels)` tuple at the same
export interval — a "duplicate/out-of-order point" / minimum-sampling-period error). The
PID suffix gives each writer its own series. This still differs from the previous
statsd+telegraf pipeline, where the telegraf sidecar aggregated across pods *and*
processes before sending to Cloud Monitoring, so there was roughly one series per
`(metric, namespace, tags)`.

Practical implications:

- Samples/minute are billed under "Prometheus Samples Ingested". With the default
  60 s export interval, each series produces one sample per minute — and there are
  `pods × processes-per-pod` series per `(metric, tags)`, so size the ingest budget
  against process count, not pod count.
- Rolling deploys create fresh pod names, and **worker recycling churns PIDs**: every
  gunicorn `max_requests` recycle or celery `max-tasks-per-child` restart spawns a new
  PID, hence a brand-new `instance` series. The old series keep appearing in queries
  until they go 25 h without a new sample, then age out — so high churn inflates active
  series and ingest cost beyond the steady-state process count.
- Per-process visibility is available in PromQL (`group by (instance)`); aggregate away
  the PID dimension (`sum without (instance) (...)`) for pod- or service-level views.
  This granularity was not possible under the old pipeline.

If cardinality or ingest cost become a problem, the recommended path is to introduce
a collector (GKE Managed OpenTelemetry or self-managed) between the app and
`telemetry.googleapis.com` that performs aggregation/relabeling before export.
Avoid working around the issue by setting `service.instance.id` to a stable value
such as the deployment name — that silently discards pod-level observability without
making the collector path any harder to adopt later.

#### What drives the bill

- Ingestion is billed under the "Prometheus Samples Ingested" SKU, roughly
  $0.03–$0.06 per million samples depending on region, with progressive volume tiers
  (cheaper above 50B samples/month). See
  <https://cloud.google.com/products/observability/pricing>.
- **Histograms dominate.** A classic Prometheus histogram exports one series per bucket
  plus `_sum` and `_count` — with the 16 default boundaries in
  `DEFAULT_HISTOGRAM_BUCKETS` that is ~19 samples per export per tag-combination per
  process. One histogram metric therefore costs ~19× a counter.
- **Tag cardinality dominates the metric-name count.** The app has only ~22 metric
  names, but the multipliers come from tags: the `task` counter is tagged
  `name:{task.name}, state:{...}` (≈ tasks × states series per worker process), `sensor`
  is `type × provider` across tracking plugins, and `task.queue_wait` is a histogram per
  queue (~19 series × queue count).
- Ballpark at current scale (~50–80 processes per cluster, 60 s interval): order of
  500M–800M samples/month, i.e. tens of dollars per cluster per month at the top-tier
  rate.

#### Reducing ingest cost

Ordered cheapest/no-collector first, collector path last:

1. **Raise `METRICS_EXPORT_INTERVAL_MS`.** Samples scale inversely with the export
   interval; going 60 s → 120 s halves the bill with no code change (see the settings
   table above).
2. **Trim histogram buckets.** Every boundary is a separate series. Pass a narrower
   `buckets=` advisory at the call site for metrics that don't need 16-bucket resolution.
3. **Prune high-cardinality tags.** The per-task-name tag on the `task` counter and the
   per-provider tag on `sensor` are the biggest series multipliers — drop or coarsen any
   dimension nobody charts.
4. **Collector with aggregation — the structural fix, with a caveat.** A pass-through
   collector saves $0: it forwards the same series. Savings require deliberately
   configuring cross-process aggregation (delta conversion → aggregate away the
   PID/`instance` dimension → re-emit cumulative, e.g. the `cumulativetodelta`/`interval`
   processor chain) — cumulative counters from different processes cannot simply be
   summed by dropping a label. With that configured, series collapse by roughly the
   process count, but a self-managed 2-replica collector gateway costs ~$10–20/month in
   node resources, which roughly cancels the ingest savings at current scale. The
   collector pays off as cardinality grows, or for the operational wins (auth/IAM out of
   the app, central relabel/drop rules, cardinality caps).

### Future direction: Managed OpenTelemetry on GKE

GKE offers a managed in-cluster OpenTelemetry collector at
`http://opentelemetry-collector.gke-managed-otel.svc.cluster.local:4318`, which
accepts OTLP from workloads and forwards signals to Cloud Monitoring, Cloud Trace,
and Cloud Logging on the pod's behalf. When that is enabled cluster-wide, the
`GCPOTLPMetricExporter` and its ADC handling can be replaced by the stock
`OTLPMetricExporter` reading the `OTEL_EXPORTER_OTLP_ENDPOINT` environment variable
that GKE auto-injects, and the application no longer needs IAM bindings for
`monitoring.metricWriter` (the managed collector's own service account carries those).

On topology: unlike the previous telegraf pipeline — a statsd sidecar on every pod plus
a central aggregation pod, a two-tier shape forced by statsd being UDP to localhost —
OTLP is HTTP to a cluster Service, so a collector deployment is a single tier: either
the GKE managed collector (zero pods to run) or one small self-managed gateway
Deployment (~2 replicas) per cluster. No per-pod sidecars, no second aggregation tier.

[^export-diagnostic]: One exception: `GCPOTLPMetricExporter._export()` overrides the
    parent's *private* `_export` method as a temporary rollout diagnostic. The stock OTLP
    exporter logs only the HTTP status code on a failed export, but the GCP Telemetry
    API's response *body* is what distinguishes a missing `roles/monitoring.metricWriter`,
    a wrong quota project, the API not being enabled, or a rejected `location` label — so
    the override logs the first 2 KB of any ≥400 response body. Because it couples to a
    private upstream method (its signature is kept variadic since it differs across SDK
    versions), it should be removed — or formally adopted with the TEMP marker dropped —
    once metrics are confirmed flowing in production.

## Logging

### Overview

Logging is configured in `das_server.log` via a Python `logging.config.dictConfig`
dictionary called `DEFAULT_LOGGING`. `init_logging()` is called from the gunicorn
`post_fork` hook so each worker applies the configuration once, guarded by a module-
level `has_initialized` flag.

### Format

All log output goes to stdout through a single `console` handler using the
`utils.log.CloudLogsJsonFormatter`. The JSON format is parsed by Google Cloud Logging
when the container's stdout is scraped, so `levelname`, `name`, `message`, thread,
and process are preserved as structured fields rather than being left as a plain
text line.

### Log levels

Per-logger levels are environment-configurable so they can be tuned per deployment
without a code change:

| Logger | Env variable | Default |
| --- | --- | --- |
| `django` | `DJANGO_LOGGING_LEVEL` | `INFO` |
| `django.request` | `DJANGO_REQUEST_LOGGING_LEVEL` | `INFO` |
| `django.server` | `DJANGO_SERVER_LOGGING_LEVEL` | `INFO` |
| `rt_api` | `RTAPI_LOGGING_LEVEL` | `WARNING` |
| `rt_api.socketio` | `RTAPI_SOCKET_LOGGING_LEVEL` | `WARNING` |
| `rt_api.pubsub_listener` | `RTAPI_PUBSUB_LOGGING_LEVEL` | `WARNING` |
| root (`""`) | `ROOT_LOGGING_LEVEL` | `WARNING` |
| `PIL.Image` | — | `WARNING` |
| `opentelemetry` | — | `WARNING` |

The `opentelemetry` logger is pinned to `WARNING` so routine export activity and
debug chatter from the SDK and instrumentation packages does not flood production
logs. Export failures still surface as warnings or errors.

### Local overrides

`das_server/log.py` attempts to import a sibling `local_log.py` module. If present,
`init_logging()` reads the named logging config from that module instead of
`das_server.log`. This is the escape hatch for developer environments that want a
different formatter, verbose SDK logging, or file handlers, without editing the
shared file.
