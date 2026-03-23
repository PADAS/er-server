from observations.celery_tile_invalidation import _task_may_use_tile_invalidation_batch


def test_celery_tile_invalidation_task_prefix_filter():
    assert _task_may_use_tile_invalidation_batch("observations.tasks.recompute_observation_segments_task")
    assert _task_may_use_tile_invalidation_batch("tracking.tasks.run_source_plugin")
    assert _task_may_use_tile_invalidation_batch("rt_api.tasks.handle_new_source_observation")
    assert _task_may_use_tile_invalidation_batch("analyzers.tasks.handle_subject")
    assert not _task_may_use_tile_invalidation_batch("das_server.tasks.refresh_tenants_cache")
    assert not _task_may_use_tile_invalidation_batch("utils.auth0.tasks.refresh_cached_auth0_jwks")
