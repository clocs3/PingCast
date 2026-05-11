import redis

from app.core.config import settings


def get_redis():
    if settings.REDIS_URL:
        return redis.Redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_timeout=settings.ROUTE_LOOKUP_TIMEOUT_SECONDS,
        )

    return redis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        password=settings.REDIS_PASSWORD or None,
        ssl=settings.REDIS_SSL,
        decode_responses=True,
        socket_timeout=settings.ROUTE_LOOKUP_TIMEOUT_SECONDS,
    )
