from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    POSTGRES_DB: str = ""
    POSTGRES_USER: str = ""
    POSTGRES_PASSWORD: str = ""

    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432
    POSTGRES_URL: str = ""

    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_URL: str = ""
    REDIS_PASSWORD: str = ""
    REDIS_SSL: bool = False
    REDIS_SOCKET_TIMEOUT_SECONDS: float = 2.0
    MONGO_URI: str = ""
    MONGO_DB_NAME: str = "streaming"
    MONGO_COLLECTION_VOD: str = "user_vods"

    CACHE_TTL_SECONDS: int = 120
    FAIL_TTL_SECONDS: int = 300
    FAIL_LIMIT: int = 5

    K8S_NAMESPACE: str = "default"
    FFMPEG_IMAGE: str = "my-ffmpeg-hls:example"
    FFMPEG_SIDECAR_IMAGE: str = "my-s3-uploader:example"
    HLS_PVC_NAME: str = ""
    HLS_HOST_PATH: str = ""
    FFMPEG_PULL_POLICY: str = "IfNotPresent"
    FFMPEG_IMAGE_PULL_SECRET: str = ""
    FFMPEG_SERVICE_ACCOUNT_NAME: str = "stream-controller"
    FFMPEG_JOB_TTL_SECONDS: int = 300
    FFMPEG_STARTUP_DELAY_SECONDS: float = 1.0
    FFMPEG_TERMINATION_GRACE_SECONDS: int = 30
    DISCONNECT_GRACE_SECONDS: int = 10
    FFMPEG_NODE_SELECTOR_KEY: str = ""
    FFMPEG_NODE_SELECTOR_VALUE: str = ""
    FFMPEG_NODE_TAINT_KEY: str = ""
    FFMPEG_NODE_TAINT_VALUE: str = ""
    FFMPEG_NODE_TAINT_EFFECT: str = "NoSchedule"
    FFMPEG_REQUEST_CPU: str = "500m"
    FFMPEG_REQUEST_MEMORY: str = "1Gi"
    FFMPEG_LIMIT_CPU: str = "2"
    FFMPEG_LIMIT_MEMORY: str = "2Gi"
    SIDECAR_REQUEST_CPU: str = "100m"
    SIDECAR_REQUEST_MEMORY: str = "128Mi"
    SIDECAR_LIMIT_CPU: str = "500m"
    SIDECAR_LIMIT_MEMORY: str = "512Mi"

    RTMP_HOST: str = "nginx-rtmp.ns-media.svc.cluster.local"
    RTMP_PORT: int = 1935
    RTMP_APP: str = "live"
    HLS_OUTPUT_ROOT: str = "/hls"
    HLS_CLEANUP_ON_START: bool = True
    HLS_CLEANUP_ON_EXIT: bool = True

    OBJECT_STORAGE_PROVIDER: str = "s3"
    OBJECT_STORAGE_BUCKET: str = "pingcast-media-archive-example"
    OBJECT_STORAGE_PREFIX: str = "hls"
    OBJECT_STORAGE_ENDPOINT: str = ""
    OBJECT_STORAGE_ACCESS_KEY: str = ""
    OBJECT_STORAGE_SECRET_KEY: str = ""
    OBJECT_STORAGE_SECURE: bool = False
    OBJECT_STORAGE_AUTO_CREATE_BUCKET: bool = False
    AWS_REGION: str = "ap-northeast-2"
    VOD_PUBLIC_BASE_URL: str = "https://vod.example.com"

    HLS_SEGMENT_SECONDS: int = 6
    UPLOAD_POLL_SECONDS: int = 2
    SIDECAR_IDLE_EXIT_SECONDS: int = 45
    UPLOAD_WORKERS: int = 4


settings = Settings()
