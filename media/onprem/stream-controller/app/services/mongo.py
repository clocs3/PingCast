import hashlib
from typing import Optional

from pymongo import MongoClient
from pymongo.collection import Collection

from app.core.config import settings

_client: Optional[MongoClient] = None


def _stream_id(stream_key: str) -> str:
    return hashlib.sha256(stream_key.encode("utf-8")).hexdigest()[:16]


def _get_collection() -> Optional[Collection]:
    global _client

    if not settings.MONGO_URI:
        return None

    if _client is None:
        _client = MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=2000)

    db = _client[settings.MONGO_DB_NAME]
    return db[settings.MONGO_COLLECTION_VOD]


def save_vod_record(
    user_id: int,
    stream_key: str,
    started_at: int,
    ended_at: int,
    vod_object_key: str,
    title: str,
    category: str,
) -> None:
    collection = _get_collection()
    if collection is None:
        return

    relative_prefix = f"{user_id}/{started_at}"
    playback_url = f"{settings.VOD_PUBLIC_BASE_URL.rstrip('/')}/{relative_prefix}/vod.m3u8"
    thumbnail_url = f"{settings.VOD_PUBLIC_BASE_URL.rstrip('/')}/{relative_prefix}/thumbnail.jpg"
    vod_doc = {
        "user_id": user_id,
        "stream_id": _stream_id(stream_key),
        "started_at": started_at,
        "ended_at": ended_at,
        "vod_url": playback_url,
        "playback_url": playback_url,
        "thumbnail_url": thumbnail_url,
        "vod_path": f"{relative_prefix}/vod.m3u8",
        "thumbnail_path": f"{relative_prefix}/thumbnail.jpg",
        "vod_object_key": vod_object_key,
    }
    if title:
        vod_doc["title"] = title
    if category:
        vod_doc["category"] = category

    collection.update_one(
        {"user_id": user_id, "started_at": started_at},
        {"$set": vod_doc},
        upsert=True,
    )
