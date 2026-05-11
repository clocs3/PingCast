import hashlib

from app.services.redis import get_redis
from app.services.postgres import get_user_by_stream_key
from app.core.config import settings


def _stream_key_hash(stream_key: str) -> str:
    return hashlib.sha256(stream_key.encode("utf-8")).hexdigest()


def verify_stream_key(stream_key: str) -> int:
    r = get_redis()

    cache_key = f"cache:stream_key:{_stream_key_hash(stream_key)}"
    user_id = r.get(cache_key)
    if user_id:
        return int(user_id)

    user_id = get_user_by_stream_key(stream_key)
    r.setex(cache_key, settings.CACHE_TTL_SECONDS, user_id)
    return user_id
