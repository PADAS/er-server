# Events-Create Rate Limiting

EarthRanger applies two complementary per-tenant guards to `POST /api/v1.0/activity/events/`:

1. **Rate throttle** — a batch-weighted sliding-window throttle that limits the number of event
   units created per minute (a single POST creating N events consumes N units).
2. **Concurrency cap** — a maximum number of simultaneously in-flight event-create requests.

Both guards protect worker and database-connection-pool resources from burst traffic.  They are
controlled by a shared kill-switch (`EVENTS_CREATE_THROTTLE_ENABLED`), which is **disabled by
default** and enabled per-cluster as part of a staged rollout (see
["Global kill-switch"](#3-global-kill-switch--events_create_throttle_enabled) below).

The rate throttle's count is **approximate under concurrent workers**: each worker reads, checks,
and writes the shared cache entry non-atomically, so under a concurrent burst from the same tenant
the count can over-admit past the configured limit (see "Why this exists" below). The concurrency
cap is the primary protection against burst-driven lock contention; the rate throttle is a
secondary, coarser guard.

## Why this exists

Every event created via that endpoint acquires a per-tenant PostgreSQL advisory lock (keyed by
tenant + model) during serial-number assignment (`core/mixins.py:_save_with_serial_number`).
Under a burst of concurrent POSTs from one tenant, requests queue on that lock while each holds a
worker and a DB connection.  Both guards address this from complementary angles:

* The **rate throttle** rejects excess requests cheaply — before any lock is acquired — and returns
  HTTP 429 with a `Retry-After` header. Its count is a non-atomic cache read-modify-write done
  per-worker, so it is a coarse backstop rather than a strict atomic counter: under exactly the
  concurrent-burst shape this guard targets, it can over-admit past the configured limit.
* The **concurrency cap** limits how many requests can hold a worker simultaneously, regardless of
  the per-minute rate, and is not subject to the same race — it is the primary protection against
  burst-driven lock contention.  A production incident showed ~100 concurrent single-event POSTs
  driving serial-number advisory lock contention to 168 s max request time even at a modest
  64 req/min.  The rate limit alone (600/min) would not have bounded this.

## Default rate

**600 event units per minute** per tenant.  Because the throttle is batch-weighted, a single POST
that creates N events consumes N units — not 1.  The limit is intentionally generous; it is
designed to absorb normal usage spikes while preventing accidental or adversarial connection-pool
exhaustion.

## Batch semantics

The events endpoint accepts a JSON array (batch) as well as a single object.  A batch of **N**
events consumes **N** units from the rate-limit bucket, because N serial-number locks will be
acquired.  A batch that would exceed the remaining budget is rejected in its entirety with a 429
response.

### Example

With a limit of `600/min` and 598 units already consumed:

| Request | Batch size | Outcome |
|---------|-----------|---------|
| POST (single event) | 1 | 201 — consumes unit 599 |
| POST (single event) | 1 | 201 — consumes unit 600 |
| POST (single event) | 1 | **429** — budget exhausted |
| POST (batch of 2) | 2 | **429** — only 0 units remain this window; the batch needs 2. It will succeed once the window resets, since 2 is within the 600-unit bucket. |

A batch larger than the entire bucket (more than `num_requests` units — e.g. 601 events against a `600/min` limit) can **never** succeed, no matter how long the client waits. In that case the 429 response omits the `Retry-After` header, signalling that the client should reduce the batch size rather than retry.

## Configuration

There are three independent configuration surfaces.  They interact as described below.

### 1. Multi-tenant rate — TMS (`eventsCreateThrottleRate`)

For each tenant managed by TMS, set the `eventsCreateThrottleRate` field in the TMS
environment-settings JSON.  The value is a standard DRF rate string such as `"600/min"` or
`"3600/hour"`.  This is the authoritative rate for multi-tenant deployments; it is populated into
`EnvironmentSettings.events_create_throttle_rate` at startup.

### 2. Single-tenant / development rate — `EVENTS_CREATE_THROTTLE_RATE`

For single-tenant or local-development instances (where TMS is not serving per-tenant config),
set the Django setting or environment variable:

```
EVENTS_CREATE_THROTTLE_RATE=600/min
```

The default when the variable is absent is `"600/min"`.

Setting this to an empty string or the sentinel value `"none"` (case-insensitive) disables
throttling for that deployment **only** — it does **not** override a rate supplied by TMS for
tenants in a multi-tenant deployment.

```
EVENTS_CREATE_THROTTLE_RATE=
# or
EVENTS_CREATE_THROTTLE_RATE=none
```

### 3. Global kill-switch — `EVENTS_CREATE_THROTTLE_ENABLED`

`EVENTS_CREATE_THROTTLE_ENABLED` is a boolean Django setting, **opt-in and disabled (`False`) by
default**. Both guards are no-ops until it is explicitly set to `True`. Setting it to `True`
enables throttling **for every tenant on the instance**, subject to the per-tenant TMS value or
`EVENTS_CREATE_THROTTLE_RATE` as described above. This is intended for a staged, per-cluster
rollout — each cluster's ArgoCD-managed env vars flip the guards on independently — rather than a
single global cutover.

```
EVENTS_CREATE_THROTTLE_ENABLED=true
```

The kill-switch is checked first in `get_rate()` (rate throttle) and in `_get_concurrency_limit()`
(concurrency cap), before any tenant lookup is performed, so it adds no overhead when disabled.

### Summary: which setting wins?

| Scenario | Rate throttle | Concurrency cap |
|---|---|---|
| `EVENTS_CREATE_THROTTLE_ENABLED=false` (default) | Disabled | Disabled |
| `EVENTS_CREATE_THROTTLE_ENABLED=true` + TMS supplies values | TMS rate applies | TMS limit applies |
| `EVENTS_CREATE_THROTTLE_ENABLED=true` + no TMS + Django settings | Django setting applies | Django setting applies |
| `EVENTS_CREATE_THROTTLE_RATE=` (empty) / `EVENTS_CREATE_MAX_CONCURRENCY=0` | No rate throttle | No concurrency cap |

---

## Concurrency cap

### Default limit

**10 simultaneous in-flight event-create requests** per tenant, across all workers and pods.

### Configuration

Configured via TMS field `eventsCreateMaxConcurrency` (for multi-tenant deployments) or the
Django setting / environment variable:

```
EVENTS_CREATE_MAX_CONCURRENCY=10
```

Setting this to `0` or any negative number disables the concurrency cap for that deployment.

### How it works

The concurrency cap uses a Redis sorted set (one key per tenant).  Each request enters with:

1. **ZADD** — add a member for this request (UUID) with the current epoch as score.
2. **ZREMRANGEBYSCORE** — evict entries older than 180 seconds (self-healing against leaked slots
   from crashed workers).
3. **ZCARD** — count live in-flight entries.
4. If `count > limit`, remove our own entry and return 429.  Otherwise proceed.
5. On exit (success, exception, or validation error), **ZREM** removes our entry.

The 180-second TTL is set generously above the observed worst-case request time.  An `EXPIRE`
is also set on the key itself as a last-resort safety net.

The guard fails **open**: if Redis is unreachable, the request is allowed and a warning is logged.

### Redis key naming

The concurrency guard uses `get_redis_connection("default")` (raw connection) which bypasses the
Django cache `KEY_FUNCTION`.  The tenant prefix is therefore applied manually:

```
{tenant_id}:events_create_inflight
```

This is documented in AGENTS.md under "Tenant-scoped cache and lock keys" as a known exception.

### HTTP response on concurrency cap exceeded

```
HTTP/1.1 429 Too Many Requests
Retry-After: 5
Content-Type: application/json

{"detail": "Too many concurrent event-create requests for this tenant. Please retry after a moment."}
```

The `Retry-After` value is a small fixed advisory (5 seconds).  Unlike the rate throttle, there is
no predictable window-reset time for a concurrency cap, so a short backoff suggestion is used.

---

## GET requests are never throttled or capped

Only `POST` requests are subject to either guard.  `GET /api/v1.0/activity/events/` (list) is
always exempt.

## Tenant isolation

Both guards are per-tenant.

* **Rate throttle** — uses a constant cache-key suffix (`"tenant"`) under the `default` cache
  alias, which has `KEY_FUNCTION = utils.tenant.cache.make_cache_key`.  The function prepends the
  thread-local tenant ID automatically.
* **Concurrency cap** — uses the manually prefixed Redis key `{tenant_id}:events_create_inflight`.

There is no cross-tenant interference.

## Observability

Both guards emit OTel counters via `utils.stats.increment` (metric emission is best-effort and
never affects the request path). The `scope` prefix (`events_create`) is derived from
`TenantEventCreateThrottleBase.scope`, so a future patrol-equivalent throttle gets its own
metric names automatically.

| Metric | Fired when | Tags |
|---|---|---|
| `events_create.throttled` | The rate throttle rejects a request (batch would exceed the bucket). | `tenant` (tenant id, or `"unknown"` if it could not be resolved), `batch_size` |
| `events_create.concurrency_rejected` | The concurrency cap rejects a request (in-flight count exceeds the limit). | `tenant`, `batch_size`, `limit` (the configured concurrency limit) |
| `events_create.fail_open` | The concurrency guard fails open instead of enforcing the cap. | `tenant` (absent when the tenant itself could not be resolved), `reason` — one of `tenant_unresolved`, `redis_error`, `non_redis_backend` |

The `reason` tag on `events_create.fail_open` distinguishes: the tenant could not be resolved
(`tenant_unresolved`); a genuine Redis failure (`redis_error`, also logged per-occurrence at
WARNING); or the default cache backend is not django-redis (`non_redis_backend`, logged once per
process to avoid log spam on every POST — the metric still fires on every occurrence).

## Extensibility

Both guards are implemented in `das/activity/throttles.py`.

* **Rate throttle** — `EventCreateThrottle` extends `TenantEventCreateThrottleBase`.  To add a
  similar throttle for another resource (e.g. patrols), subclass `TenantEventCreateThrottleBase`
  and set `env_settings_field` to the appropriate `EnvironmentSettings` attribute.
* **Concurrency cap** — `EventCreateConcurrencyMixin` and `_event_create_concurrency_slot` can
  serve as a template for a patrol-create concurrency guard with a different Redis key name and
  `EnvironmentSettings` field.
