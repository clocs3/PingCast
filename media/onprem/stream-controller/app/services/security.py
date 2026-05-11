import hashlib

from app.services.redis import get_redis
from app.core.config import settings


def _stream_key_hash(stream_key: str) -> str:
    return hashlib.sha256(stream_key.encode("utf-8")).hexdigest()


def record_fail(stream_key: str):
    r = get_redis()
    key = f"security:fail:{_stream_key_hash(stream_key)}"
    count = r.incr(key)
    if count == 1:
        r.expire(key, settings.FAIL_TTL_SECONDS)

def is_blocked(stream_key: str) -> bool:
    r = get_redis()
    count = r.get(f"security:fail:{_stream_key_hash(stream_key)}")
    return bool(count and int(count) >= settings.FAIL_LIMIT)
