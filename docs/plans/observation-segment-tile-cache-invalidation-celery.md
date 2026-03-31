# Plan: async observation-segment vector tile cache invalidation (Celery)

## Context

Synchronous `post_save` handlers (see `observations/signals_segments_cache.py`) batch tile invalidation and flush on transaction commit, but each observation/segment/status save still pays for batch bookkeeping, `transaction.on_commit` registration, and (after commit) Redis `SCAN`/`DELETE` work. Bulk sensor ingestion was slowed enough that **signal registration is no longer loaded at app startup**; implementation lives in `observations/segment_tile_cache_invalidation.py` for reuse.

## Goals

- Move invalidation off the request/task hot path while preserving correctness for map clients (stale tiles acceptable only within a bounded window).
- Avoid per-row Redis work during bulk observation posts.
- Keep a single place for tile-math and key invalidation (`invalidate_tile_cache_keys`) so behavior stays consistent.

## Proposed design

### 1. Task API

- Add a Celery task, e.g. `invalidate_segment_tile_cache_for_tenant`, accepting:
  - `tenant_id` (required)
  - **Either** a list of point specs `(lon, lat)` **or** segment specs `(lon1, lat1, lon2, lat2)` (or a small union type serialized as JSON).
- Optional: `zooms` override (default: same as `SEGMENTS_TILE_INVALIDATION_ZOOMS`).
- The task body calls existing helpers: expand to `(tenant_id, z, x, y)`, dedupe in-process, then call `invalidate_tile_cache_keys` per unique cell (or batch deletes if Redis client supports it later).

### 2. Producers (who enqueues)

- **Observations API / bulk create path:** after successful commit (or in `transaction.on_commit`), enqueue **one** task per tenant per request (or per batch) with the set of affected geometries, instead of N signal invocations.
- **Segment recompute / backfills:** enqueue from `recompute_observation_segments` (or parallel tasks per batch of IDs) so heavy backfills do not block the process.
- **SubjectStatus:** same pattern as observations if the map must reflect status dots immediately; otherwise consider coalescing with a short debounce (see below).

### 3. Coalescing and load control

- **Dedupe:** merge duplicate `(tenant_id, z, x, y)` inside the task (already how batched flush works).
- **Debounce (optional):** for high-frequency tenants, use Redis `SET key NX EX ttl` or a DB row to skip enqueue if a “full tenant bump” task ran recently; alternatively enqueue a single “bump `vector_tile_data_version` for tenant” task if coarse invalidation is acceptable (check `utils.cache` versioning semantics).
- **Rate limits:** apply Celery `rate_limit` or queue routing so invalidation cannot starve critical queues.

### 4. Ordering and correctness

- Tasks must run **after** the DB transaction that wrote observations/segments is visible (use `on_commit` when enqueueing from request handlers).
- Stale reads: document that tiles may be wrong for seconds until the worker runs; acceptable for most wildlife map use cases or mitigated by shorter TTL on tile cache keys.

### 5. Re-enable selective sync invalidation (optional)

- If some code paths need immediate consistency (e.g. admin UI), call `segment_tile_cache_invalidation._invalidate_for_point` or enqueue a high-priority task from that path only.

### 6. Cleanup

- Decide whether `signals_segments_cache` should be deleted, replaced by explicit `connect_*` for dev-only, or kept only for tests.
- Revisit `celery_tile_invalidation.connect_celery_tile_invalidation_cleanup`: if nothing uses connection-local batching in workers, the `task_prerun` hook could be removed for a tiny savings.

### 7. Testing

- Unit tests: task expands points/segments to expected tile set (reuse tests in `test_segment_cache_invalidation.py` for geometry).
- Integration: enqueue from `on_commit` in a test transaction; assert Redis keys cleared after worker runs (or mock broker and assert payload).

## Rollout

1. Ship with signals disconnected (current state); monitor tile staleness and cache hit rate.
2. Add task + enqueue from hottest path (bulk observation ingest) first.
3. Add segment/status producers and tuning (debounce, rate limits) based on metrics.
