import json
import threading
import time
from datetime import datetime, timezone

from fastapi import FastAPI
from app.api import rtmp
from app.core.config import settings
from app.services.ffmpeg import reconcile_live_hls_routes
from app.services.redis import get_redis

CONTROL_META_KEY = "control:meta"
CONTROL_EVENT_POLL_SECONDS = 2

try:
    from app.observability import setup_observability
except Exception:
    def setup_observability(app: FastAPI) -> None:
        return

try:
    from prometheus_fastapi_instrumentator import Instrumentator
except Exception:
    Instrumentator = None

app = FastAPI()
setup_observability(app)
if Instrumentator is not None:
    Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
app.include_router(rtmp.router)


def _run_hls_route_reconcile_loop() -> None:
    while True:
        try:
            reconcile_live_hls_routes()
        except Exception as exc:
            print(f"[HLS ROUTE LOOP ERROR] {repr(exc)}")
        time.sleep(settings.HLS_ROUTE_RECONCILE_SECONDS)


def _run_control_event_log_loop() -> None:
    seen_marker = None
    while True:
        try:
            redis = get_redis()
            meta = redis.hgetall(CONTROL_META_KEY)
            marker = (
                meta.get("last_action_at", ""),
                meta.get("last_action", ""),
                meta.get("last_result", ""),
            )
            if seen_marker is None:
                seen_marker = marker
            elif marker != seen_marker and meta.get("last_action_at"):
                action = meta.get("last_action")
                action_at = meta.get("last_action_at")
                try:
                    action_at_iso = datetime.fromtimestamp(int(action_at), tz=timezone.utc).isoformat()
                except Exception:
                    action_at_iso = ""
                print(
                    json.dumps(
                        {
                            "event": "control_transition",
                            "action": action,
                            "action_at": action_at,
                            "action_at_iso": action_at_iso,
                            "service": (action or "").split("_", 1)[0],
                            "transition_kind": "trigger" if (action or "").endswith("_on") else "recover",
                            "source": meta.get("last_action_source"),
                            "result": meta.get("last_result"),
                            "reason": meta.get("last_reason"),
                            "route53_change_id": meta.get("last_route53_change_id"),
                            "steering_enabled": meta.get("steering_enabled"),
                            "burst_enabled": meta.get("burst_enabled"),
                        },
                        separators=(",", ":"),
                    )
                )
                seen_marker = marker
        except Exception as exc:
            print(f"[CONTROL EVENT LOOP ERROR] {repr(exc)}")
        time.sleep(CONTROL_EVENT_POLL_SECONDS)


@app.on_event("startup")
def startup_hls_route_reconcile() -> None:
    if not settings.ENABLE_HLS_ROUTE_DISCOVERY:
        return
    thread = threading.Thread(target=_run_hls_route_reconcile_loop, name="hls-route-reconcile", daemon=True)
    thread.start()


@app.on_event("startup")
def startup_control_event_log_loop() -> None:
    thread = threading.Thread(target=_run_control_event_log_loop, name="control-event-log", daemon=True)
    thread.start()


@app.get("/health")
def health():
    return {"status": "ok"}
