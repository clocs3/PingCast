from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

from app.services.redis import get_redis

LIVE_PREFIX = "live:stream:"
STEERING_ENABLED_KEY = "control:steering:enabled"
BURST_ENABLED_KEY = "control:burst:enabled"
CONTROL_META_KEY = "control:meta"
LOCAL_CLUSTER = "onprem"


def _infer_origin_cluster(data: dict[str, str]) -> str | None:
    origin_cluster = (data.get("origin_cluster") or "").strip().lower()
    if origin_cluster in {"onprem", "aws"}:
        return origin_cluster

    hls_route_status = (data.get("hls_route_status") or "").strip().lower()
    if hls_route_status in {"ready", "resolve_failed", "unsupported"}:
        return "onprem"
    if hls_route_status == "disabled":
        return "aws"

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


def _safe_count_hls_routes(*statuses: str) -> int:
    wanted = set(statuses)
    count = 0
    try:
        redis = get_redis()
        cursor = 0
        while True:
            cursor, keys = redis.scan(cursor=cursor, match=f"{LIVE_PREFIX}*", count=200)
            for key in keys:
                try:
                    route_status = redis.hget(key, "hls_route_status")
                except Exception:
                    continue
                if route_status in wanted:
                    count += 1
            if cursor == 0:
                break
    except Exception:
        return 0
    return count


def _safe_read_control_flag(key: str) -> int:
    try:
        redis = get_redis()
        value = redis.get(key)
    except Exception:
        return 0
    if value is None:
        return 0
    return 1 if value.strip().lower() == "true" else 0


def _safe_read_control_timestamp(field: str) -> int:
    try:
        redis = get_redis()
        value = redis.hget(CONTROL_META_KEY, field)
    except Exception:
        return 0
    if not value:
        return 0
    try:
        return int(value)
    except Exception:
        return 0


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

HLS_ROUTE_READY_STREAMS = Gauge(
    "hls_route_ready_streams",
    "Current number of live streams with a resolved on-prem HLS route.",
)
HLS_ROUTE_READY_STREAMS.set_function(lambda: _safe_count_hls_routes("ready"))

HLS_ROUTE_ERROR_STREAMS = Gauge(
    "hls_route_error_streams",
    "Current number of live streams whose HLS route resolution failed.",
)
HLS_ROUTE_ERROR_STREAMS.set_function(lambda: _safe_count_hls_routes("resolve_failed"))

CONTROL_STEERING_ENABLED = Gauge(
    "control_steering_enabled",
    "Current steering control state from Redis.",
)
CONTROL_STEERING_ENABLED.set_function(lambda: _safe_read_control_flag(STEERING_ENABLED_KEY))

CONTROL_BURST_ENABLED = Gauge(
    "control_burst_enabled",
    "Current burst control state from Redis.",
)
CONTROL_BURST_ENABLED.set_function(lambda: _safe_read_control_flag(BURST_ENABLED_KEY))

CONTROL_LAST_STEERING_TRIGGER_TIMESTAMP_SECONDS = Gauge(
    "control_last_steering_trigger_timestamp_seconds",
    "Unix timestamp of the most recent successful steering trigger action.",
)
CONTROL_LAST_STEERING_TRIGGER_TIMESTAMP_SECONDS.set_function(
    lambda: _safe_read_control_timestamp("last_steering_trigger_at")
)

CONTROL_LAST_STEERING_RECOVER_TIMESTAMP_SECONDS = Gauge(
    "control_last_steering_recover_timestamp_seconds",
    "Unix timestamp of the most recent successful steering recover action.",
)
CONTROL_LAST_STEERING_RECOVER_TIMESTAMP_SECONDS.set_function(
    lambda: _safe_read_control_timestamp("last_steering_recover_at")
)

CONTROL_LAST_BURST_TRIGGER_TIMESTAMP_SECONDS = Gauge(
    "control_last_burst_trigger_timestamp_seconds",
    "Unix timestamp of the most recent successful burst trigger action.",
)
CONTROL_LAST_BURST_TRIGGER_TIMESTAMP_SECONDS.set_function(
    lambda: _safe_read_control_timestamp("last_burst_trigger_at")
)

CONTROL_LAST_BURST_RECOVER_TIMESTAMP_SECONDS = Gauge(
    "control_last_burst_recover_timestamp_seconds",
    "Unix timestamp of the most recent successful burst recover action.",
)
CONTROL_LAST_BURST_RECOVER_TIMESTAMP_SECONDS.set_function(
    lambda: _safe_read_control_timestamp("last_burst_recover_at")
)

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
