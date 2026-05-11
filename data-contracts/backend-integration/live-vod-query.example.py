import os
import re

from motor.motor_asyncio import AsyncIOMotorClient
from redis_client import redis_client

STEERING_ENABLED_KEY = "control:steering:enabled"

LIVE_ORIGIN_BASE_URL = os.getenv("LIVE_ORIGIN_BASE_URL", "https://hls.example.com").rstrip("/")
LIVE_CDN_BASE_URL = os.getenv("LIVE_CDN_BASE_URL", "https://hls.example.com").rstrip("/")
VOD_BASE_URL = os.getenv("VOD_BASE_URL", "https://vod.example.com").rstrip("/")
ALLOW_STREAM_KEY_PLAYBACK_FALLBACK = os.getenv("ALLOW_STREAM_KEY_PLAYBACK_FALLBACK", "false").lower() == "true"

mongo_client = AsyncIOMotorClient(os.getenv("MONGO_URI", "<mongodb-connection-url>"))
vod_collection = mongo_client["streaming"]["user_vods"]


def _is_steering_enabled() -> bool:
    value = redis_client.get(STEERING_ENABLED_KEY)
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    return bool(value and str(value).lower() == "true")


def build_live_playback_url(stream_info: dict, fallback_stream_key: str, fallback_user_id: int | None = None) -> str:
    base_url = LIVE_CDN_BASE_URL if _is_steering_enabled() else LIVE_ORIGIN_BASE_URL
    started_at = str(stream_info.get("started_at", "")).strip()
    user_id = str(stream_info.get("user_id") or fallback_user_id or "").strip()
    if user_id and started_at:
        return f"{base_url}/{user_id}/{started_at}/index.m3u8"
    if not ALLOW_STREAM_KEY_PLAYBACK_FALLBACK:
        raise ValueError("safe live playback path requires user_id and started_at")
    return f"{base_url}/{fallback_stream_key}/index.m3u8"


def normalize_vod_item(user_id: int, vod: dict) -> dict:
    started_at = int(vod.get("started_at", 0))
    relative_prefix = f"{user_id}/{started_at}"
    vod_object_key = str(vod.get("vod_object_key") or "").strip()
    vod_path = str(vod.get("vod_path") or "").strip()

    if vod_object_key.startswith("s3://"):
        matched = re.match(r"^s3://[^/]+/(.+)$", vod_object_key)
        vod_object_key = matched.group(1) if matched else ""

    if vod_object_key and not vod_path:
        prefix = "hls/"
        vod_path = vod_object_key[len(prefix):] if vod_object_key.startswith(prefix) else vod_object_key
    if not vod_path:
        vod_path = f"{relative_prefix}/vod.m3u8"

    normalized = dict(vod)
    normalized.pop("stream_key", None)
    normalized.pop("stream_id", None)
    normalized["vod_path"] = vod_path
    normalized["playback_url"] = f"{VOD_BASE_URL}/{vod_path.lstrip('/')}"
    normalized["thumbnail_url"] = f"{VOD_BASE_URL}/{relative_prefix}/thumbnail.jpg"
    return normalized


async def list_user_vods(user_id: int, limit: int = 20, before_started_at: int | None = None) -> list[dict]:
    query = {"user_id": user_id}
    if before_started_at is not None:
        query["started_at"] = {"$lt": before_started_at}

    cursor = (
        vod_collection.find(query, {"_id": 0})
        .sort("started_at", -1)
        .limit(max(1, min(limit, 50)))
    )
    return [normalize_vod_item(user_id, vod) async for vod in cursor]
