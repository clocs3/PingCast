import ipaddress
import re
import time
from typing import Dict, Tuple

import requests
from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

from app.core.config import settings
from app.services.redis import get_redis

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

_route_cache: Dict[str, Tuple[float, str]] = {}
_LIVE_KEY_PREFIX = "live:stream:"
_SESSION_KEY_PREFIX = "hls:session:"
_TARGET_RE = re.compile(r"^[A-Za-z0-9.-]+:\d{1,5}$")
_STREAM_KEY_RE = re.compile(r"^[A-Za-z0-9_-]{8,128}$")
_FORWARDED_REQUEST_HEADERS = {
    "range",
    "if-none-match",
    "if-modified-since",
    "if-range",
    "accept",
    "accept-encoding",
    "user-agent",
}
_PASS_RESPONSE_HEADERS = {
    "content-type",
    "content-length",
    "cache-control",
    "etag",
    "last-modified",
    "accept-ranges",
    "content-range",
    "access-control-allow-origin",
    "access-control-allow-methods",
    "access-control-allow-headers",
    "access-control-expose-headers",
}
_CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
    "Access-Control-Allow-Headers": "*",
    "Access-Control-Expose-Headers": "Content-Length, Content-Range",
}


def _invalidate_route_target(stream_key: str) -> None:
    _route_cache.pop(stream_key, None)


def _decode_redis_mapping(data: Dict[str, str] | Dict[bytes, bytes]) -> Dict[str, str]:
    if not data:
        return {}
    if isinstance(next(iter(data.keys())), (bytes, bytearray)):
        return {k.decode(): v.decode() for k, v in data.items()}
    return data


def _sanitize_route_target(target: str | None) -> str | None:
    if not target:
        return None
    candidate = target.strip()
    if not _TARGET_RE.match(candidate):
        return None

    host, port_text = candidate.rsplit(":", 1)
    try:
        port = int(port_text)
    except ValueError:
        return None
    if port <= 0 or port > 65535:
        return None

    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        allowed_suffixes = tuple(
            suffix.strip()
            for suffix in settings.HLS_ALLOWED_HOST_SUFFIXES.split(",")
            if suffix.strip()
        )
        if allowed_suffixes and not host.endswith(allowed_suffixes):
            return None
        return candidate

    if address.is_loopback or address.is_link_local or address.is_multicast or address.is_unspecified:
        return None
    if address.is_global and not settings.ALLOW_PUBLIC_HLS_TARGETS:
        return None
    return candidate


def _validate_stream_key(stream_key: str) -> None:
    if not _STREAM_KEY_RE.match(stream_key):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid stream key")


def _validate_asset_path(asset_path: str) -> None:
    if asset_path.startswith("/") or ".." in asset_path.split("/"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid hls asset path")


def _rehydrate_route_target(stream_key: str) -> str | None:
    live_key = f"{_LIVE_KEY_PREFIX}{stream_key}"
    live_data = _decode_redis_mapping(get_redis().hgetall(live_key) or {})
    if live_data.get("status") != "running":
        return None

    target = _sanitize_route_target(live_data.get("hls_route_target", ""))
    if not target:
        return None

    route_key = f"{settings.ROUTE_KEY_PREFIX}{stream_key}"
    try:
        get_redis().set(route_key, target, ex=max(settings.ROUTE_CACHE_TTL_SECONDS * 12, 60))
    except Exception:
        pass
    return target


def _load_route_target(stream_key: str, *, force_refresh: bool = False) -> str | None:
    now = time.monotonic()
    cached = _route_cache.get(stream_key)
    if not force_refresh and cached and cached[0] > now:
        return cached[1]

    route_key = f"{settings.ROUTE_KEY_PREFIX}{stream_key}"
    target = _sanitize_route_target(get_redis().get(route_key))
    if not target:
        target = _rehydrate_route_target(stream_key)
        if not target:
            _route_cache.pop(stream_key, None)
            return None

    _route_cache[stream_key] = (now + settings.ROUTE_CACHE_TTL_SECONDS, target)
    return target


def _load_stream_key_for_session(user_id: str, started_at: str) -> str | None:
    session_key = f"{_SESSION_KEY_PREFIX}{user_id}:{started_at}"
    stream_key = get_redis().get(session_key)
    if stream_key:
        return stream_key

    for live_key in get_redis().scan_iter(f"{_LIVE_KEY_PREFIX}*", count=200):
        data = _decode_redis_mapping(get_redis().hgetall(live_key) or {})
        if data.get("status") != "running":
            continue
        if str(data.get("user_id", "")).strip() != user_id:
            continue
        if str(data.get("started_at", "")).strip() != started_at:
            continue
        stream_key = live_key.split(":")[-1]
        try:
            get_redis().set(session_key, stream_key, ex=max(settings.ROUTE_CACHE_TTL_SECONDS * 12, 60))
        except Exception:
            pass
        return stream_key
    return None


def _response_headers(upstream_response: requests.Response) -> Dict[str, str]:
    return {
        key: value
        for key, value in upstream_response.headers.items()
        if key.lower() in _PASS_RESPONSE_HEADERS and key.lower() != "content-length"
    }


def _request_upstream(request: Request, target: str, stream_key: str, asset_path: str) -> requests.Response:
    upstream_url = f"http://{target}/{stream_key}/{asset_path}"
    if request.url.query:
        upstream_url = f"{upstream_url}?{request.url.query}"

    return requests.request(
        method=request.method,
        url=upstream_url,
        headers={
            key: value
            for key, value in request.headers.items()
            if key.lower() in _FORWARDED_REQUEST_HEADERS
        },
        timeout=settings.UPSTREAM_TIMEOUT_SECONDS,
        stream=True,
    )


def _proxy_hls_asset(request: Request, stream_key: str, asset_path: str) -> Response:
    if request.method == "OPTIONS":
        return Response(status_code=status.HTTP_204_NO_CONTENT, headers=_CORS_HEADERS)
    _validate_stream_key(stream_key)
    _validate_asset_path(asset_path)

    target = _load_route_target(stream_key)
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="hls route not found")

    try:
        upstream_response = _request_upstream(request, target, stream_key, asset_path)
    except requests.RequestException:
        _invalidate_route_target(stream_key)
        refreshed_target = _load_route_target(stream_key, force_refresh=True)
        if not refreshed_target:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="hls route not found")
        try:
            upstream_response = _request_upstream(request, refreshed_target, stream_key, asset_path)
        except requests.RequestException as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="upstream request failed",
            ) from exc

    if upstream_response.status_code in {404, 502, 503, 504}:
        upstream_response.close()
        _invalidate_route_target(stream_key)
        refreshed_target = _load_route_target(stream_key, force_refresh=True)
        if refreshed_target and refreshed_target != target:
            try:
                upstream_response = _request_upstream(request, refreshed_target, stream_key, asset_path)
            except requests.RequestException as exc:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="upstream request failed",
                ) from exc

    headers = _response_headers(upstream_response)
    headers.update(_CORS_HEADERS)
    if request.method == "HEAD":
        upstream_response.close()
        return Response(status_code=upstream_response.status_code, headers=headers)

    return StreamingResponse(
        upstream_response.iter_content(chunk_size=64 * 1024),
        status_code=upstream_response.status_code,
        headers=headers,
        media_type=upstream_response.headers.get("content-type"),
        background=BackgroundTask(upstream_response.close),
    )


def _maybe_proxy_session_asset(request: Request, first_segment: str, asset_path: str) -> Response | None:
    if "/" not in asset_path:
        return None
    started_at, nested_asset_path = asset_path.split("/", 1)
    if not first_segment.isdigit() or not started_at.isdigit() or not nested_asset_path:
        return None

    stream_key = _load_stream_key_for_session(first_segment, started_at)
    if not stream_key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="hls session not found")
    return _proxy_hls_asset(request, stream_key, nested_asset_path)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.api_route("/{stream_key}/{asset_path:path}", methods=["GET", "HEAD", "OPTIONS"])
def proxy_hls_root(request: Request, stream_key: str, asset_path: str):
    session_response = _maybe_proxy_session_asset(request, stream_key, asset_path)
    if session_response is not None:
        return session_response
    if not settings.ALLOW_STREAM_KEY_PLAYBACK_FALLBACK:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="hls session not found")
    return _proxy_hls_asset(request, stream_key, asset_path)


@app.api_route("/hls/{stream_key}/{asset_path:path}", methods=["GET", "HEAD", "OPTIONS"])
def proxy_hls_prefixed(request: Request, stream_key: str, asset_path: str):
    session_response = _maybe_proxy_session_asset(request, stream_key, asset_path)
    if session_response is not None:
        return session_response
    if not settings.ALLOW_STREAM_KEY_PLAYBACK_FALLBACK:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="hls session not found")
    return _proxy_hls_asset(request, stream_key, asset_path)
