from __future__ import annotations

import logging
import time
import uuid
from contextlib import contextmanager
from enum import Enum
from typing import Iterator

import redis
from django_redis import get_redis_connection

from django.conf import settings
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle

from utils import stats
from utils.tenant import get_tenant_settings

logger = logging.getLogger(__name__)

# Entries older than this are treated as stale (crashed-worker self-healing).
# Set generously above the observed worst-case request time.
_CONCURRENCY_SLOT_TTL_SECONDS: int = 180

# Fixed Retry-After value (seconds) returned on concurrency-cap rejections.
# There is no clean window-reset time for a concurrency cap, so a small
# advisory value is returned to encourage the client to back off briefly.
_CONCURRENCY_RETRY_AFTER_SECONDS: int = 5


def _request_batch_size(request: Request) -> int:
    """Return the number of events in the payload (minimum 1).

    Shared by the rate throttle and the concurrency guard so both report the
    same batch size for a given request.
    """
    data = request.data
    if isinstance(data, list):
        return max(len(data), 1)
    return 1


# ---------------------------------------------------------------------------
# Rate throttle
# ---------------------------------------------------------------------------


class TenantEventCreateThrottleBase(SimpleRateThrottle):
    """Base class for per-tenant, batch-weighted POST throttles.

    Subclasses must set ``env_settings_field`` to the name of the
    ``EnvironmentSettings`` attribute that holds the DRF rate string for that
    resource (e.g. ``"events_create_throttle_rate"``).

    Design decisions
    ----------------
    * **POST only** — ``get_cache_key`` returns ``None`` for every method that
      is not POST, which makes DRF skip throttle enforcement entirely for reads.
    * **Tenant-wide, not per-user** — the cache key is a constant ``"tenant"``
      string.  The ``default`` cache alias is configured with
      ``KEY_FUNCTION = utils.tenant.cache.make_cache_key``, which prepends the
      thread-local tenant id automatically.  Do *not* add tenant_id to the key
      here — that would double-prefix the Redis key.
    * **Batch weighting** — each POST may carry a list of N events.  The
      throttle deducts N units from the bucket instead of 1, because N serial-
      number advisory locks will be acquired.  ``allow_request`` checks
      ``len(history) + N > num_requests`` in-process per worker; under concurrent
      workers the count may slightly overshoot.  This throttle is a coarse
      backstop, not a strict atomic counter.  If the batch would exceed the
      remaining budget the whole request is rejected before any lock is acquired.
    * **Opt-out** — returning ``None`` from ``get_rate()`` tells DRF to skip
      enforcement entirely.  Two independent disable paths exist:

      - *Global kill-switch* (``EVENTS_CREATE_THROTTLE_ENABLED``, opt-in and
        ``False`` by default) — must be explicitly set to ``True`` for either
        guard to run; overrides every per-tenant TMS value and every env-var
        rate when left at its default. Checked first; no tenant lookup is
        performed.
      - *Per-rate sentinel* — an empty/falsy value or the string ``"none"``
        (case-insensitive) in ``env_settings`` or ``EVENTS_CREATE_THROTTLE_RATE``
        disables throttling for single-tenant / dev deployments only; it does
        **not** override a rate supplied by TMS in multi-tenant deployments.
    """

    scope = "events_create"

    #: Subclasses set this to the EnvironmentSettings field that holds the rate.
    env_settings_field: str = ""

    def get_rate(self) -> str | None:
        # Global kill-switch: opt-in and disabled by default. Must be
        # explicitly enabled (per-cluster, staged rollout) before throttling
        # applies to any tenant on this instance.
        if not getattr(settings, "EVENTS_CREATE_THROTTLE_ENABLED", False):
            return None
        if not self.env_settings_field:
            return None
        try:
            rate = getattr(get_tenant_settings().env_settings, self.env_settings_field, None)
            if not rate or rate.lower() == "none":
                return None
            return rate
        except Exception:
            logger.warning(
                "Failed to resolve tenant throttle rate for field %r",
                self.env_settings_field,
                exc_info=True,
            )
            return None

    def get_cache_key(self, request: Request, view: object) -> str | None:
        """Return a constant key for POST; ``None`` (no throttle) otherwise."""
        if request.method != "POST":
            return None
        # A constant ident means all users of this tenant share one bucket.
        # The cache KEY_FUNCTION prefixes the key with the tenant id, so two
        # tenants never collide.
        return self.cache_format % {
            "scope": self.scope,
            "ident": "tenant",
        }

    def _batch_size(self, request: Request) -> int:
        """Return the number of events in the payload (minimum 1)."""
        return _request_batch_size(request)

    def allow_request(self, request: Request, view: object) -> bool:
        """Allow the request only if there is sufficient budget for the batch.

        Overrides DRF's ``SimpleRateThrottle.allow_request`` to consume N units
        (where N = batch size) instead of 1.  The check ``len(history) + N >
        num_requests`` is done in-process per worker and may slightly overshoot
        under concurrent workers — this throttle is a coarse backstop, not a
        strict atomic counter.  If any event in the batch would exceed the budget
        the whole request is rejected before any lock is acquired.

        The batch size is stashed on ``self._batch`` so that ``wait()`` can
        compute the correct Retry-After for the whole batch.

        For non-POST methods ``get_cache_key`` returns ``None``, so DRF's parent
        implementation returns ``True`` immediately and this method is never
        reached.
        """
        if self.rate is None:
            return True

        self.key = self.get_cache_key(request, view)
        if self.key is None:
            return True

        self.history = self.cache.get(self.key, [])
        self.now = self.timer()

        # Evict expired entries.
        while self.history and self.history[-1] <= self.now - self.duration:
            self.history.pop()

        batch = self._batch_size(request)
        # Stash for use in wait() — the batch size determines how many slots
        # must expire before a retry of the same batch can succeed.
        self._batch = batch

        # Reject if the batch would exceed the bucket.
        if len(self.history) + batch > self.num_requests:
            try:
                tenant_id: object = get_tenant_settings().id
            except Exception:
                tenant_id = "unknown"
            stats.increment(
                f"{self.scope}.throttled",
                tags={"tenant": str(tenant_id), "batch_size": str(batch)},
            )
            return self.throttle_failure()

        # Record all N units in one cache write.
        self.history = [self.now] * batch + self.history
        self.cache.set(self.key, self.history, self.duration)
        return True

    def wait(self) -> float | None:
        """Return seconds until enough slots free up to fit the current batch.

        DRF's default ``wait()`` returns the time until a *single* slot opens,
        which is too optimistic when the rejected request carries a batch of N —
        the client would retry, get rejected again (N-1 times), and only succeed
        once N slots have all expired.

        This override finds the N-th oldest history entry (where N = batch size
        stashed by ``allow_request``) and returns the time until *that* entry
        expires, i.e. the moment at which the window has enough free capacity for
        the whole batch.

        The empty-history case falls back to DRF's default ``wait()`` behaviour
        as a defensive measure, but it is unreachable in practice — see the
        inline comment below. A batch larger than the remaining history simply
        clamps to the oldest available entry.
        """
        batch = getattr(self, "_batch", 1)

        # A batch larger than the bucket itself can never fit, no matter how
        # long the client waits — even a full, empty bucket has only
        # num_requests slots.  Return None so DRF emits no Retry-After header
        # and the client is not misled into retrying an unsatisfiable request.
        if batch > self.num_requests:
            return None

        if not self.history:
            # Defensive fallback, matching DRF's default wait() for an empty
            # history. Unreachable in practice: batch is always >= 1, so a
            # rejection with an empty history implies batch > num_requests,
            # which returned None above.
            return self.duration / float(self.num_requests + 1)

        # history is stored newest-first; history[-k] is the k-th oldest
        # entry. Clamp to the history length so we never index out of range.
        effective_batch = min(batch, len(self.history))
        oldest_needed = self.history[-effective_batch]
        return self.duration - (self.now - oldest_needed)


class EventCreateThrottle(TenantEventCreateThrottleBase):
    """Per-tenant rate limit for ``POST /api/v1.0/activity/events/``.

    The rate is read from ``EnvironmentSettings.events_create_throttle_rate``
    (populated from TMS JSON field ``eventsCreateThrottleRate`` or the Django
    setting ``EVENTS_CREATE_THROTTLE_RATE``).  Default is ``"600/min"``.

    A single POST that carries a batch of N events consumes N units from the
    bucket, because each event acquires a per-tenant PostgreSQL advisory lock
    during serial-number assignment.
    """

    env_settings_field: str = "events_create_throttle_rate"


# ---------------------------------------------------------------------------
# Concurrency cap
# ---------------------------------------------------------------------------


def _concurrency_redis_key(tenant_id: object) -> str:
    """Build the Redis sorted-set key for the tenant's in-flight request gauge.

    NOTE: ``get_redis_connection`` bypasses the Django cache KEY_FUNCTION, so
    the tenant prefix MUST be applied manually here.  See AGENTS.md
    "Tenant-scoped cache and lock keys".
    """
    return f"{tenant_id}:events_create_inflight"


def _get_concurrency_limit() -> int | None:
    """Return the effective concurrency limit, or None if disabled.

    Returns ``None`` when:
    - the global kill-switch ``EVENTS_CREATE_THROTTLE_ENABLED`` is not
      explicitly enabled (opt-in; ``False`` by default), or
    - ``EVENTS_CREATE_MAX_CONCURRENCY`` (or the per-tenant TMS value) is <= 0.

    Per-tenant TMS value wins over the Django setting for multi-tenant
    deployments; the Django setting is the single-tenant/dev default.
    """
    if not getattr(settings, "EVENTS_CREATE_THROTTLE_ENABLED", False):
        return None

    limit: int = getattr(settings, "EVENTS_CREATE_MAX_CONCURRENCY", 10)
    try:
        tenant_limit = get_tenant_settings().env_settings.events_create_max_concurrency
        if tenant_limit is not None:
            limit = tenant_limit
    except Exception:
        logger.warning("Failed to resolve tenant concurrency limit", exc_info=True)

    return limit if limit > 0 else None


class _SlotClaimOutcome(Enum):
    """Result of attempting to claim a concurrency slot in Redis."""

    CLAIMED = "claimed"
    REJECTED = "rejected"
    FAIL_OPEN = "fail_open"


# Set once a non-django-redis default cache backend has been detected, so the
# WARNING is logged only once per process instead of on every POST. A simple
# module-global is sufficient here: this only guards log spam, so a benign
# race that logs twice under concurrent first-requests is acceptable.
_non_redis_backend_warning_logged: bool = False


def _log_non_redis_backend_once() -> None:
    """Log, at most once per process, that the concurrency guard is failing
    open because the default cache backend does not expose a raw Redis
    connection (i.e. it is not django-redis)."""
    global _non_redis_backend_warning_logged
    if not _non_redis_backend_warning_logged:
        logger.warning(
            "Default cache backend does not support raw Redis connections; "
            "events-create concurrency guard will fail open for this process "
            "(further occurrences are suppressed).",
        )
        _non_redis_backend_warning_logged = True


def _try_claim_slot(
    redis_key: str, request_id: str, limit: int
) -> tuple[_SlotClaimOutcome, redis.Redis | None, str | None]:
    """Attempt to claim an in-flight slot for *request_id* in the tenant's
    Redis sorted set, returning ``(outcome, redis_connection, fail_open_reason)``.

    ``fail_open_reason`` is ``None`` unless *outcome* is ``FAIL_OPEN``, in which
    case it is one of ``"redis_error"`` or ``"non_redis_backend"``.

    All Redis-related exceptions are caught and translated into a FAIL_OPEN
    outcome here — this function never raises for Redis-related failures, and
    it never yields, so the caller (a generator-based context manager) can
    call it without any risk of a caller exception being mis-caught at a
    ``yield`` point.
    """
    now_ts = time.time()
    stale_cutoff = now_ts - _CONCURRENCY_SLOT_TTL_SECONDS

    try:
        redis_conn = get_redis_connection("default")
    except NotImplementedError:
        # Raised by django_redis.get_redis_connection when the configured
        # "default" cache is not a django-redis backend (e.g. LocMemCache in
        # dev). This is a static deployment characteristic, not a transient
        # failure, so it is logged once per process rather than per request.
        _log_non_redis_backend_once()
        return _SlotClaimOutcome.FAIL_OPEN, None, "non_redis_backend"
    except redis.exceptions.RedisError:
        logger.warning(
            "Redis unavailable for concurrency guard on events-create; failing open",
            exc_info=True,
        )
        return _SlotClaimOutcome.FAIL_OPEN, None, "redis_error"

    try:
        # Atomically: add our slot, evict stale entries, count live entries.
        pipe = redis_conn.pipeline()
        pipe.zadd(redis_key, {request_id: now_ts})
        pipe.zremrangebyscore(redis_key, "-inf", stale_cutoff)
        pipe.zcard(redis_key)
        # Set a TTL on the key itself as a last-resort safety net.
        pipe.expire(redis_key, _CONCURRENCY_SLOT_TTL_SECONDS * 2)
        _, _, count, _ = pipe.execute()

        if count > limit:
            # We're over the limit — remove our own entry and reject.
            redis_conn.zrem(redis_key, request_id)
            return _SlotClaimOutcome.REJECTED, redis_conn, None

        return _SlotClaimOutcome.CLAIMED, redis_conn, None

    except redis.exceptions.RedisError:
        # If the ZADD reached Redis before a later command in the pipeline (or
        # pipe.execute() itself) failed, our entry may already be persisted in
        # the sorted set. Best-effort clean it up now so we don't leak the slot
        # until the stale-eviction TTL — the connection may be dead, so this is
        # allowed to fail silently; TTL eviction remains the backstop.
        try:
            redis_conn.zrem(redis_key, request_id)
        except redis.exceptions.RedisError:
            pass
        logger.warning(
            "Redis unavailable for concurrency guard on events-create; failing open",
            exc_info=True,
        )
        return _SlotClaimOutcome.FAIL_OPEN, None, "redis_error"


@contextmanager
def _event_create_concurrency_slot(request: Request) -> Iterator[Response | None]:
    """Context manager that claims an in-flight slot for a POST, yields ``None``
    on success, or yields a 429 ``Response`` when the cap is reached.

    Uses a Redis sorted set keyed by tenant id.  Members are unique request
    UUIDs; scores are Unix epoch seconds.  Entries older than
    ``_CONCURRENCY_SLOT_TTL_SECONDS`` are evicted on every enter, providing
    self-healing against slots leaked by crashed workers.

    The raw Redis connection (``get_redis_connection``) is used deliberately:
    the Django cache KEY_FUNCTION is bypassed here, so the tenant prefix is
    applied by ``_concurrency_redis_key``.  If Redis is unreachable, or the
    default cache is not a django-redis backend, the context manager fails
    open (allows the request).

    Non-POST methods are a no-op (yield ``None`` immediately).

    No ``yield`` statement below is inside a ``try``/``except`` that catches
    caller exceptions — the Redis-specific try/except blocks live entirely
    inside ``_try_claim_slot``, which never yields. This matters because an
    exception raised by the caller's ``with``-body is thrown back into this
    generator at whichever ``yield`` is currently suspended; if that yield
    sat inside a broad ``except Exception``, the caller's exception would be
    mis-caught, mis-logged as a Redis failure, and swallowed — leaving the
    generator to raise ``RuntimeError: generator didn't stop after throw()``
    instead of propagating the caller's original exception.
    """
    if request.method != "POST":
        yield None
        return

    limit = _get_concurrency_limit()
    if limit is None:
        yield None
        return

    request_id = str(uuid.uuid4())

    try:
        tenant_id: object = get_tenant_settings().id
    except Exception:
        logger.warning("Could not resolve tenant for concurrency guard; failing open", exc_info=True)
        stats.increment(f"{TenantEventCreateThrottleBase.scope}.fail_open", tags={"reason": "tenant_unresolved"})
        yield None
        return

    redis_key = _concurrency_redis_key(tenant_id)
    outcome, redis_conn, fail_reason = _try_claim_slot(redis_key, request_id, limit)

    if outcome is _SlotClaimOutcome.FAIL_OPEN:
        stats.increment(
            f"{TenantEventCreateThrottleBase.scope}.fail_open",
            tags={"tenant": str(tenant_id), "reason": fail_reason or "unknown"},
        )
        yield None
        return

    if outcome is _SlotClaimOutcome.REJECTED:
        batch = _request_batch_size(request)
        stats.increment(
            f"{TenantEventCreateThrottleBase.scope}.concurrency_rejected",
            tags={"tenant": str(tenant_id), "batch_size": str(batch), "limit": str(limit)},
        )
        response = Response(
            {"detail": ("Too many concurrent event-create requests for this tenant. " "Please retry after a moment.")},
            status=status.HTTP_429_TOO_MANY_REQUESTS,
            headers={"Retry-After": str(_CONCURRENCY_RETRY_AFTER_SECONDS)},
        )
        yield response
        return

    # CLAIMED: hold the slot for the caller's with-body, then release it. The
    # ``finally`` neither catches nor suppresses any exception the body raises
    # — it only guarantees the ``zrem`` runs before the exception propagates.
    try:
        yield None
    finally:
        try:
            redis_conn.zrem(redis_key, request_id)
        except redis.exceptions.RedisError:
            logger.warning(
                "Failed to release concurrency slot for request %s; slot will expire in %ds",
                request_id,
                _CONCURRENCY_SLOT_TTL_SECONDS,
                exc_info=True,
            )


class EventCreateConcurrencyMixin:
    """View mixin that enforces the per-tenant in-flight concurrency cap.

    Apply to any ``APIView`` subclass that handles event creation.  The mixin
    wraps ``post()`` so the concurrency slot is always released — including on
    exception and validation-error paths — via a ``try/finally`` in the
    context manager.

    GET and other read methods are completely unaffected.

    Structure for reuse: a patrol equivalent can subclass this mixin (or use
    ``_event_create_concurrency_slot`` directly with a patrol-specific key)
    without touching this class.
    """

    def post(self, request: Request, *args, **kwargs) -> Response:
        with _event_create_concurrency_slot(request) as rejection:
            if rejection is not None:
                return rejection
            # super() has no statically-known base (this is a standalone mixin);
            # at runtime it resolves to the concrete APIView this is mixed into,
            # which defines post(). Hence the ignore is safe.
            return super().post(request, *args, **kwargs)  # type: ignore[misc]
