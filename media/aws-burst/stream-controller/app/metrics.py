from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

from app.services.redis import get_redis

LIVE_PREFIX = "live:stream:"
LOCAL_CLUSTER = "aws"


def _infer_origin_cluster(data: dict[str, str]) -> str | None:
    origin_cluster = (data.get("origin_cluster") or "").strip().lower()
    if origin_cluster in {"onprem", "aws"}:
        return origin_cluster

    return None


def _safe_scan_live_statuses(*statuses: str) -> int:
    wanted = set(statuses)
    count = 0
    try:
        redis = get_redis()
        cursor = 0
        while True:
            cursor, keys = redis.scan(cursor=cursor, match=f"{LIVE_PREFIX}*", count=200)
            for key in keys:
                try:
                    data = redis.hgetall(key)
                except Exception:
                    continue
                if _infer_origin_cluster(data) != LOCAL_CLUSTER:
                    continue
                status = data.get("status")
                if status in wanted:
                    count += 1
            if cursor == 0:
                break
    except Exception:
        return 0
    return count


ACTIVE_PUBLISHERS = Gauge(
    "active_publishers",
    "Current number of active publishers observed by stream-controller.",
)
ACTIVE_PUBLISHERS.set_function(lambda: _safe_scan_live_statuses("ffmpeg_pending", "running"))

FFMPEG_PENDING_STREAMS = Gauge(
    "ffmpeg_pending_streams",
    "Current number of streams waiting for ffmpeg startup to complete.",
)
FFMPEG_PENDING_STREAMS.set_function(lambda: _safe_scan_live_statuses("ffmpeg_pending"))

FFMPEG_START_FAILURES_TOTAL = Counter(
    "ffmpeg_start_failures_total",
    "Total number of ffmpeg startup failures.",
)

FFMPEG_START_LATENCY_SECONDS = Histogram(
    "ffmpeg_start_latency_seconds",
    "Time from on_publish acceptance to ffmpeg job startup success.",
    buckets=(0.25, 0.5, 1, 2, 5, 10, 20, 30, 60),
)


def observe_ffmpeg_start_success(latency_seconds: float) -> None:
    FFMPEG_START_LATENCY_SECONDS.observe(max(latency_seconds, 0.0))


def observe_ffmpeg_start_failure() -> None:
    FFMPEG_START_FAILURES_TOTAL.inc()
