import re
import time
from typing import Any, Dict, Optional
from urllib.parse import unquote

from fastapi import APIRouter, Request, Response, BackgroundTasks, status

from app.services.auth import verify_stream_key
from app.services.ffmpeg import (
    resolve_hls_route_target,
    start_ffmpeg_container,
    stop_ffmpeg_container,
)
from app.services.mongo import save_vod_record
from app.services.redis import get_redis
from app.services.security import is_blocked, record_fail
from app.services.vod_playlist import build_and_upload_vod_playlist
from app.core.config import settings
from app.metrics import observe_ffmpeg_start_failure, observe_ffmpeg_start_success

router = APIRouter()
STREAM_KEY_RE = re.compile(r"^[A-Za-z0-9_-]{8,128}$")

LIVE_PREFIX = "live:stream:"
LOCK_PREFIX = "lock:ffmpeg:"
DONE_PREFIX = "done:vod:"
PENDING_DONE_PREFIX = "pending:done:"
HLS_ROUTE_PREFIX = "hls:route:"
HLS_SESSION_PREFIX = "hls:session:"

LIVE_TTL_SECONDS = 60 * 60 * 2
LOCK_TTL_SECONDS = LIVE_TTL_SECONDS
DONE_TTL_SECONDS = 60 * 60 * 24

ENABLE_STOP_ON_DONE = True


def _build_vod_prefix(user_id: int, started_at: int) -> str:
    object_prefix = settings.OBJECT_STORAGE_PREFIX.strip("/")
    if object_prefix:
        return f"{object_prefix}/{user_id}/{started_at}"
    return f"{user_id}/{started_at}"


def _pick_first_value(data: Dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = data.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _build_vod_url_with_retries(vod_prefix: str, retries: int = 3, delay_seconds: int = 2) -> str:
    last_error: Exception | None = None
    for _ in range(retries):
        try:
            return build_and_upload_vod_playlist(vod_prefix)
        except Exception as e:
            last_error = e
            time.sleep(delay_seconds)
    if last_error is not None:
        raise last_error
    raise ValueError("failed to build vod playlist")


def _finalize_stream_if_pending(
    stream_key: str,
    expected_started_at: str,
) -> None:
    time.sleep(settings.DISCONNECT_GRACE_SECONDS)

    r = get_redis()
    live_key = f"{LIVE_PREFIX}{stream_key}"
    lock_key = f"{LOCK_PREFIX}{stream_key}"
    done_key_base = f"{DONE_PREFIX}{stream_key}:"
    pending_key = f"{PENDING_DONE_PREFIX}{stream_key}"
    route_key = f"{HLS_ROUTE_PREFIX}{stream_key}"

    pending_started_at = r.get(pending_key)
    if pending_started_at != expected_started_at:
        return

    data = r.hgetall(live_key) or {}
    if data and isinstance(next(iter(data.keys())), (bytes, bytearray)):
        data = {k.decode(): v.decode() for k, v in data.items()}

    current_started_at = str(data.get("started_at", ""))
    if current_started_at != expected_started_at:
        r.delete(pending_key)
        return

    container_name = data.get("container_name")
    if ENABLE_STOP_ON_DONE and container_name:
        try:
            stop_ffmpeg_container(container_name)
        except Exception as e:
            print(f"[FFMPEG STOP ERROR] stream_key={_mask_stream_key(stream_key)}, error={repr(e)}")

    user_id = data.get("user_id")
    session_key = f"{HLS_SESSION_PREFIX}{user_id}:{expected_started_at}" if user_id and expected_started_at else ""
    vod_prefix = data.get("vod_prefix")
    title = _pick_first_value(
        data,
        (
            "broadcast_title",
            "title",
            "live_title",
            "stream_title",
        ),
    )
    category = _pick_first_value(
        data,
        (
            "broadcast_category",
            "category",
            "live_category",
            "stream_category",
        ),
    )
    ended_at = int(time.time())

    if user_id and vod_prefix and expected_started_at:
        done_key = f"{done_key_base}{expected_started_at}"
        if r.setnx(done_key, 1):
            r.expire(done_key, DONE_TTL_SECONDS)
            vod_object_key = ""
            try:
                vod_object_key = _build_vod_url_with_retries(vod_prefix)
            except Exception as e:
                print(f"[VOD PLAYLIST ERROR] stream_key={_mask_stream_key(stream_key)}, error={repr(e)}")
            if vod_object_key:
                save_vod_record(
                    user_id=int(user_id),
                    stream_key=stream_key,
                    started_at=int(expected_started_at),
                    ended_at=ended_at,
                    vod_object_key=vod_object_key,
                    title=title,
                    category=category,
                )
    r.delete(live_key)
    r.delete(route_key)
    if session_key:
        r.delete(session_key)
    r.delete(lock_key)
    r.delete(pending_key)


async def _collect_params(request: Request) -> Dict[str, Any]:
    """
    nginx-rtmp notify는 환경에 따라
    - POST form(body)
    - querystring
    둘 중 하나로 들어올 수 있으니 둘 다 수집.
    """
    params: Dict[str, Any] = dict(request.query_params)

    if request.method.upper() == "POST":
        ctype = request.headers.get("content-type", "")
        if "application/x-www-form-urlencoded" in ctype or "multipart/form-data" in ctype:
            form = await request.form()
            for k, v in form.items():
                params.setdefault(k, v)

    return params


def _extract_stream_key(params: Dict[str, Any]) -> Optional[str]:
    raw = params.get("name") or params.get("stream_key") or params.get("key")
    if raw is None:
        return None

    key = unquote(str(raw)).strip()
    key = key.split("?", 1)[0].strip()
    if not STREAM_KEY_RE.match(key):
        return None
    return key or None


def _mask_stream_key(stream_key: Optional[str]) -> str:
    if not stream_key:
        return ""
    if len(stream_key) <= 8:
        return "***"
    return f"{stream_key[:4]}...{stream_key[-4:]}"


def _safe_log_params(params: Dict[str, Any]) -> Dict[str, Any]:
    redacted = dict(params)
    for key in ("name", "stream_key", "key"):
        if key in redacted:
            redacted[key] = "<redacted>"
    return redacted


@router.api_route("/on_publish", methods=["POST", "GET"])
async def on_publish(request: Request, background_tasks: BackgroundTasks):
    """
    nginx-rtmp on_publish handler

    Policy:
    - Reject missing stream keys with 403.
    - Reject failed stream-key verification with 403.
    - Start ffmpeg asynchronously after the RTMP publish request is accepted.
    """

    params = await _collect_params(request)
    stream_key = _extract_stream_key(params)

    print("[RTMP] on_publish params =", _safe_log_params(params))
    print("[RTMP] on_publish stream_key =", _mask_stream_key(stream_key))

    if not stream_key:
        return Response(content="missing stream key", status_code=status.HTTP_403_FORBIDDEN)
    try:
        blocked = is_blocked(stream_key)
    except Exception:
        blocked = False
    if blocked:
        return Response(content="too many failed attempts", status_code=status.HTTP_403_FORBIDDEN)

    try:
        user_id = verify_stream_key(stream_key)
    except Exception:
        try:
            record_fail(stream_key)
        except Exception:
            pass
        return Response(content="unauthorized", status_code=status.HTTP_403_FORBIDDEN)

    rtmp_pod_ip = request.client.host if request.client else ""
    background_tasks.add_task(safe_start_ffmpeg, stream_key, user_id, params, rtmp_pod_ip)

    return Response(content="OK", status_code=status.HTTP_200_OK)


def safe_start_ffmpeg(
    stream_key: str,
    user_id: int,
    params: Dict[str, Any],
    rtmp_pod_ip: str = "",
):
    """
    Start the ffmpeg Job with duplicate-start protection and a short startup delay.
    """

    r = get_redis()
    lock_key = f"{LOCK_PREFIX}{stream_key}"
    live_key = f"{LIVE_PREFIX}{stream_key}"
    pending_key = f"{PENDING_DONE_PREFIX}{stream_key}"
    route_key = f"{HLS_ROUTE_PREFIX}{stream_key}"

    try:
        if r.hget(live_key, "status") == "running":
            r.hset(
                live_key,
                mapping={
                    "origin_cluster": "onprem",
                    "app": str(params.get("app", "")),
                    "addr": str(params.get("addr", "")),
                    "clientid": str(params.get("clientid", "")),
                    "rtmp_pod_ip": rtmp_pod_ip,
                },
            )
            r.expire(live_key, LIVE_TTL_SECONDS)
            if r.exists(route_key):
                r.expire(route_key, LIVE_TTL_SECONDS)
            r.delete(pending_key)
            return
    except Exception:
        pass

    if not r.setnx(lock_key, 1):
        return
    r.expire(lock_key, LOCK_TTL_SECONDS)

    try:
        start_started = time.monotonic()
        r.hset(
            live_key,
            mapping={
                "user_id": user_id,
                "origin_cluster": "onprem",
                "status": "ffmpeg_pending",
                "app": str(params.get("app", "")),
                "addr": str(params.get("addr", "")),
                "clientid": str(params.get("clientid", "")),
            },
        )
        r.expire(live_key, LIVE_TTL_SECONDS)

        time.sleep(settings.FFMPEG_STARTUP_DELAY_SECONDS)
        started_at = int(time.time())
        vod_prefix = _build_vod_prefix(user_id=user_id, started_at=started_at)
        session_key = f"{HLS_SESSION_PREFIX}{user_id}:{started_at}"

        container_name = start_ffmpeg_container(
            stream_key=stream_key,
            user_id=user_id,
            started_at=started_at,
            rtmp_host=rtmp_pod_ip or settings.RTMP_HOST,
        )

        hls_route_target = ""
        hls_route_status = "disabled"
        hls_route_error = ""
        if settings.ENABLE_HLS_ROUTE_DISCOVERY:
            hls_route_status = "resolve_failed"
            try:
                hls_route_target = resolve_hls_route_target(container_name)
                r.set(route_key, hls_route_target, ex=LIVE_TTL_SECONDS)
                r.set(session_key, stream_key, ex=LIVE_TTL_SECONDS)
                hls_route_status = "ready"
            except Exception as route_error:
                if hasattr(route_error, "status") or hasattr(route_error, "reason"):
                    hls_route_error = (
                        f"{type(route_error).__name__}"
                        f"(status={getattr(route_error, 'status', None)}, "
                        f"reason={getattr(route_error, 'reason', None)}, "
                        f"body={getattr(route_error, 'body', None)!r})"
                    )
                else:
                    hls_route_error = repr(route_error)
                print(
                    f"[HLS ROUTE ERROR] stream_key={_mask_stream_key(stream_key)}, job={container_name}, error={hls_route_error}"
                )
                try:
                    r.delete(route_key)
                except Exception:
                    pass
                try:
                    r.delete(session_key)
                except Exception:
                    pass
        else:
            try:
                r.delete(route_key)
            except Exception:
                pass
            try:
                r.set(session_key, stream_key, ex=LIVE_TTL_SECONDS)
            except Exception:
                pass

        r.hset(
            live_key,
            mapping={
                "user_id": user_id,
                "origin_cluster": "onprem",
                "container_name": container_name,
                "status": "running",
                "started_at": str(started_at),
                "vod_prefix": vod_prefix,
                "app": str(params.get("app", "")),
                "addr": str(params.get("addr", "")),
                "clientid": str(params.get("clientid", "")),
                "rtmp_pod_ip": rtmp_pod_ip,
                "hls_route_target": hls_route_target,
                "hls_route_status": hls_route_status,
                "hls_route_error": hls_route_error,
            },
        )
        r.expire(live_key, LIVE_TTL_SECONDS)
        observe_ffmpeg_start_success(time.monotonic() - start_started)

    except Exception as e:
        print(f"[FFMPEG ERROR] stream_key={_mask_stream_key(stream_key)}, error={repr(e)}")
        observe_ffmpeg_start_failure()

        try:
            r.hset(
                live_key,
                mapping={
                    "user_id": user_id,
                    "origin_cluster": "onprem",
                    "status": "ffmpeg_start_failed",
                    "error": repr(e),
                    "failed_at": str(int(time.time())),
                },
            )
            r.expire(live_key, 60 * 10)
        except Exception:
            pass

        try:
            r.delete(route_key)
        except Exception:
            pass
        try:
            started_at = r.hget(live_key, "started_at")
            if started_at:
                r.delete(f"{HLS_SESSION_PREFIX}{user_id}:{started_at}")
        except Exception:
            pass

        try:
            r.delete(lock_key)
        except Exception:
            pass


@router.api_route("/on_done", methods=["POST", "GET"])
async def on_done(request: Request, background_tasks: BackgroundTasks):
    """
    nginx-rtmp on_done handler

    Always return 200 to keep nginx-rtmp callback handling stable.
    Internal cleanup failures are logged and retried through state reconciliation.
    """

    params = await _collect_params(request)
    stream_key = _extract_stream_key(params)

    print("[RTMP] on_done params =", _safe_log_params(params))
    print("[RTMP] on_done stream_key =", _mask_stream_key(stream_key))

    if not stream_key:
        return Response(content="OK", status_code=status.HTTP_200_OK)

    r = get_redis()
    live_key = f"{LIVE_PREFIX}{stream_key}"
    pending_key = f"{PENDING_DONE_PREFIX}{stream_key}"

    data: Dict[str, Any] = {}
    try:
        data = r.hgetall(live_key) or {}
        if data and isinstance(next(iter(data.keys())), (bytes, bytearray)):
            data = {k.decode(): v.decode() for k, v in data.items()}
    except Exception:
        pass

    done_clientid = str(params.get("clientid", "")).strip()
    publisher_clientid = str(data.get("clientid", "")).strip()
    if done_clientid and publisher_clientid and done_clientid != publisher_clientid:
        return Response(content="OK", status_code=status.HTTP_200_OK)

    started_at = str(data.get("started_at", "")).strip()
    if not started_at:
        return Response(content="OK", status_code=status.HTTP_200_OK)

    if r.setnx(pending_key, started_at):
        r.expire(pending_key, settings.DISCONNECT_GRACE_SECONDS + 30)
        background_tasks.add_task(_finalize_stream_if_pending, stream_key, started_at)

    return Response(content="OK", status_code=status.HTTP_200_OK)
