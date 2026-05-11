from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_URL: str = ""
    REDIS_PASSWORD: str = ""
    REDIS_SSL: bool = False

    ROUTE_KEY_PREFIX: str = "hls:route:"
    ROUTE_CACHE_TTL_SECONDS: int = 10
    ROUTE_LOOKUP_TIMEOUT_SECONDS: float = 2.0
    UPSTREAM_TIMEOUT_SECONDS: float = 10.0
    ALLOW_PUBLIC_HLS_TARGETS: bool = False
    ALLOW_STREAM_KEY_PLAYBACK_FALLBACK: bool = False
    HLS_ALLOWED_HOST_SUFFIXES: str = ".svc,.svc.cluster.local"


settings = Settings()
