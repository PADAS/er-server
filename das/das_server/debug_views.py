import gc
import os
import sys
import time
import tracemalloc

from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from activity.materialized_view import invalid_eventtypes
from utils.memoize import _all_caches

_process_start_time = time.monotonic()
_previous_snapshot = None
_tracemalloc_started = False


def _ensure_tracemalloc():
    """Start tracemalloc lazily on first endpoint hit (avoids OOM during migrations)."""
    global _tracemalloc_started
    if not _tracemalloc_started and not tracemalloc.is_tracing():
        tracemalloc.start(1)
    _tracemalloc_started = True


def _get_current_rss_mb():
    """Get current RSS (not peak) in MB."""
    if sys.platform == "linux":
        try:
            with open("/proc/self/status") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        return round(int(line.split()[1]) / 1024, 2)  # KB to MB
        except OSError:
            pass
    # Fallback: macOS or /proc unavailable — use getrusage (peak RSS)
    import resource

    ru_maxrss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        return round(ru_maxrss / (1024 * 1024), 2)  # bytes to MB
    return round(ru_maxrss / 1024, 2)  # KB to MB


def _get_locmemcache_stats():
    """Get Django LocMemCache sizes."""
    from django.core.cache import caches

    stats = {}
    for alias in caches:
        cache = caches[alias]
        backend_class = type(cache).__name__
        if backend_class == "LocMemCache":
            stats[alias] = {
                "backend": backend_class,
                "entries": len(cache._cache),
            }
    return stats


class MemoryDebugView(APIView):
    """Debug endpoint for memory profiling. Only available when MEMORY_PROFILING_ENABLED=true."""

    permission_classes = (IsAdminUser,)

    def get(self, request):
        global _previous_snapshot

        _ensure_tracemalloc()

        # ?reset=true resets the snapshot baseline
        if request.query_params.get("reset") == "true":
            _previous_snapshot = None

        data = {}

        # Process memory usage (current RSS, not peak)
        data["memory"] = {
            "rss_mb": _get_current_rss_mb(),
            "uptime_seconds": round(time.monotonic() - _process_start_time, 1),
            "pid": os.getpid(),
        }

        # GC stats (lightweight — no gc.get_objects() which is expensive)
        data["gc"] = {
            "generation_stats": gc.get_stats(),
            "garbage_count": len(gc.garbage),
        }

        # Memoize cache sizes
        cache_info = {}
        total_entries = 0
        for func_name, caches_per_tenant in _all_caches.items():
            func_info = {}
            for tenant, cache in caches_per_tenant.items():
                func_info[tenant] = len(cache)
                total_entries += len(cache)
            cache_info[func_name] = func_info
        data["memoize_caches"] = {
            "total_entries": total_entries,
            "total_functions": len(_all_caches),
            "per_function": cache_info,
        }

        # invalid_eventtypes accumulator
        data["invalid_eventtypes_count"] = len(invalid_eventtypes)

        # Django LocMemCache stats
        data["locmemcache"] = _get_locmemcache_stats()

        # tracemalloc snapshot
        if tracemalloc.is_tracing():
            current_snapshot = tracemalloc.take_snapshot()
            current_snapshot = current_snapshot.filter_traces(
                (
                    tracemalloc.Filter(False, "<frozen importlib._bootstrap>"),
                    tracemalloc.Filter(False, "<frozen importlib._bootstrap_external>"),
                    tracemalloc.Filter(False, tracemalloc.__file__),
                )
            )

            # Top allocators
            top_stats = current_snapshot.statistics("lineno")
            data["tracemalloc"] = {
                "tracing": True,
                "traced_memory_mb": round(tracemalloc.get_traced_memory()[0] / (1024 * 1024), 2),
                "peak_memory_mb": round(tracemalloc.get_traced_memory()[1] / (1024 * 1024), 2),
                "top_allocators": [
                    {"file": str(stat.traceback), "size_kb": round(stat.size / 1024, 2), "count": stat.count}
                    for stat in top_stats[:25]
                ],
            }

            # Diff with previous snapshot
            if _previous_snapshot is not None:
                diff_stats = current_snapshot.compare_to(_previous_snapshot, "lineno")
                data["tracemalloc"]["diff_since_last_call"] = [
                    {
                        "file": str(stat.traceback),
                        "size_diff_kb": round(stat.size_diff / 1024, 2),
                        "count_diff": stat.count_diff,
                    }
                    for stat in diff_stats[:25]
                    if stat.size_diff != 0
                ]

            _previous_snapshot = current_snapshot
        else:
            data["tracemalloc"] = {
                "tracing": False,
                "hint": "Set PYTHONTRACEMALLOC=10 to enable tracemalloc",
            }

        return Response(data)
