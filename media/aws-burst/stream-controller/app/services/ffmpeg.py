import hashlib
import re

from kubernetes import client, config
from kubernetes.client.exceptions import ApiException

from app.core.config import settings


_K8S_LOADED = False


def _load_k8s_config():
    global _K8S_LOADED
    if _K8S_LOADED:
        return

    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()
    _K8S_LOADED = True


def _batch_api() -> client.BatchV1Api:
    _load_k8s_config()
    return client.BatchV1Api()


def _sanitize_stream_key(stream_key: str) -> str:
    raw = stream_key.lower()
    normalized = re.sub(r"[^a-z0-9-]", "-", raw)
    normalized = re.sub(r"-+", "-", normalized).strip("-")
    if not normalized:
        normalized = "stream"

    digest = hashlib.sha1(stream_key.encode("utf-8")).hexdigest()[:8]
    return f"{normalized[:40]}-{digest}"


def _job_name(stream_key: str) -> str:
    return f"ffmpeg-stream-{_sanitize_stream_key(stream_key)}"


def _is_terminal_job(status: client.V1JobStatus | None) -> bool:
    if not status:
        return False
    if status.succeeded and status.succeeded > 0:
        return True
    if status.failed and status.failed > 0:
        return True

    for cond in status.conditions or []:
        if cond.status == "True" and cond.type in {"Complete", "Failed"}:
            return True

    return False


def _build_job(
    stream_key: str,
    user_id: int,
    started_at: int,
    rtmp_host: str | None = None,
) -> client.V1Job:
    name = _job_name(stream_key)
    object_prefix = settings.OBJECT_STORAGE_PREFIX.strip("/")
    if object_prefix:
        session_prefix = f"{object_prefix}/{user_id}/{started_at}"
    else:
        session_prefix = f"{user_id}/{started_at}"

    env = [
        client.V1EnvVar(name="STREAM_KEY", value=stream_key),
        client.V1EnvVar(name="RTMP_HOST", value=rtmp_host or settings.RTMP_HOST),
        client.V1EnvVar(name="RTMP_PORT", value=str(settings.RTMP_PORT)),
        client.V1EnvVar(name="RTMP_APP", value=settings.RTMP_APP),
        client.V1EnvVar(name="HLS_OUTPUT_ROOT", value=settings.HLS_OUTPUT_ROOT),
        client.V1EnvVar(
            name="HLS_CLEANUP_ON_START",
            value=str(settings.HLS_CLEANUP_ON_START).lower(),
        ),
        client.V1EnvVar(
            name="HLS_CLEANUP_ON_EXIT",
            value=str(settings.HLS_CLEANUP_ON_EXIT).lower(),
        ),
    ]
    uploader_env = [
        client.V1EnvVar(name="STREAM_KEY", value=stream_key),
        client.V1EnvVar(name="HLS_OUTPUT_ROOT", value=settings.HLS_OUTPUT_ROOT),
        client.V1EnvVar(name="OBJECT_STORAGE_PROVIDER", value=settings.OBJECT_STORAGE_PROVIDER),
        client.V1EnvVar(name="OBJECT_STORAGE_BUCKET", value=settings.OBJECT_STORAGE_BUCKET),
        client.V1EnvVar(name="OBJECT_STORAGE_PREFIX", value=settings.OBJECT_STORAGE_PREFIX),
        client.V1EnvVar(name="OBJECT_STORAGE_SESSION_PREFIX", value=session_prefix),
        client.V1EnvVar(name="OBJECT_STORAGE_ENDPOINT", value=settings.OBJECT_STORAGE_ENDPOINT),
        client.V1EnvVar(name="OBJECT_STORAGE_ACCESS_KEY", value=settings.OBJECT_STORAGE_ACCESS_KEY),
        client.V1EnvVar(name="OBJECT_STORAGE_SECRET_KEY", value=settings.OBJECT_STORAGE_SECRET_KEY),
        client.V1EnvVar(name="OBJECT_STORAGE_SECURE", value=str(settings.OBJECT_STORAGE_SECURE).lower()),
        client.V1EnvVar(
            name="OBJECT_STORAGE_AUTO_CREATE_BUCKET",
            value=str(settings.OBJECT_STORAGE_AUTO_CREATE_BUCKET).lower(),
        ),
        client.V1EnvVar(name="AWS_REGION", value=settings.AWS_REGION),
        client.V1EnvVar(name="UPLOAD_POLL_SECONDS", value=str(settings.UPLOAD_POLL_SECONDS)),
        client.V1EnvVar(
            name="SIDECAR_IDLE_EXIT_SECONDS",
            value=str(settings.SIDECAR_IDLE_EXIT_SECONDS),
        ),
        client.V1EnvVar(name="UPLOAD_WORKERS", value=str(settings.UPLOAD_WORKERS)),
        client.V1EnvVar(name="SHARE_PROCESS_NAMESPACE", value="true"),
    ]

    labels = {
        "app.kubernetes.io/name": "ffmpeg-hls",
        "app.kubernetes.io/managed-by": "stream-controller",
        "stream-key-hash": _sanitize_stream_key(stream_key),
    }

    volume_mounts = [client.V1VolumeMount(name="hls-data", mount_path=settings.HLS_OUTPUT_ROOT)]
    ffmpeg_resources = client.V1ResourceRequirements(
        requests={
            "cpu": settings.FFMPEG_REQUEST_CPU,
            "memory": settings.FFMPEG_REQUEST_MEMORY,
        },
        limits={
            "cpu": settings.FFMPEG_LIMIT_CPU,
            "memory": settings.FFMPEG_LIMIT_MEMORY,
        },
    )
    uploader_resources = client.V1ResourceRequirements(
        requests={
            "cpu": settings.SIDECAR_REQUEST_CPU,
            "memory": settings.SIDECAR_REQUEST_MEMORY,
        },
        limits={
            "cpu": settings.SIDECAR_LIMIT_CPU,
            "memory": settings.SIDECAR_LIMIT_MEMORY,
        },
    )
    if settings.HLS_PVC_NAME:
        volumes = [
            client.V1Volume(
                name="hls-data",
                persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(
                    claim_name=settings.HLS_PVC_NAME,
                ),
            )
        ]
    elif settings.HLS_HOST_PATH:
        volumes = [
            client.V1Volume(
                name="hls-data",
                host_path=client.V1HostPathVolumeSource(
                    path=settings.HLS_HOST_PATH,
                    type="DirectoryOrCreate",
                ),
            )
        ]
    else:
        volumes = [
            client.V1Volume(
                name="hls-data",
                empty_dir=client.V1EmptyDirVolumeSource(),
            )
        ]

    container = client.V1Container(
        name="ffmpeg",
        image=settings.FFMPEG_IMAGE,
        image_pull_policy=settings.FFMPEG_PULL_POLICY,
        env=env,
        volume_mounts=volume_mounts,
        resources=ffmpeg_resources,
        security_context=client.V1SecurityContext(allow_privilege_escalation=False),
    )
    uploader = client.V1Container(
        name="hls-s3-uploader",
        image=settings.FFMPEG_SIDECAR_IMAGE,
        image_pull_policy=settings.FFMPEG_PULL_POLICY,
        env=uploader_env,
        volume_mounts=volume_mounts,
        resources=uploader_resources,
        security_context=client.V1SecurityContext(allow_privilege_escalation=False),
    )

    image_pull_secrets = None
    if settings.FFMPEG_IMAGE_PULL_SECRET:
        image_pull_secrets = [client.V1LocalObjectReference(name=settings.FFMPEG_IMAGE_PULL_SECRET)]

    node_selector = None
    if settings.FFMPEG_NODE_SELECTOR_KEY and settings.FFMPEG_NODE_SELECTOR_VALUE:
        node_selector = {
            settings.FFMPEG_NODE_SELECTOR_KEY: settings.FFMPEG_NODE_SELECTOR_VALUE
        }

    tolerations = None
    if settings.FFMPEG_NODE_TAINT_KEY:
        toleration = client.V1Toleration(
            key=settings.FFMPEG_NODE_TAINT_KEY,
            operator="Equal" if settings.FFMPEG_NODE_TAINT_VALUE else "Exists",
            value=settings.FFMPEG_NODE_TAINT_VALUE or None,
            effect=settings.FFMPEG_NODE_TAINT_EFFECT or None,
        )
        tolerations = [toleration]

    template = client.V1PodTemplateSpec(
        metadata=client.V1ObjectMeta(labels=labels),
        spec=client.V1PodSpec(
            restart_policy="Never",
            share_process_namespace=True,
            service_account_name=settings.FFMPEG_SERVICE_ACCOUNT_NAME,
            termination_grace_period_seconds=settings.FFMPEG_TERMINATION_GRACE_SECONDS,
            containers=[container, uploader],
            volumes=volumes,
            image_pull_secrets=image_pull_secrets,
            node_selector=node_selector,
            tolerations=tolerations,
        ),
    )

    spec = client.V1JobSpec(
        template=template,
        backoff_limit=0,
        ttl_seconds_after_finished=settings.FFMPEG_JOB_TTL_SECONDS,
    )

    return client.V1Job(
        metadata=client.V1ObjectMeta(name=name, labels=labels),
        spec=spec,
    )


def start_ffmpeg_container(
    stream_key: str,
    user_id: int,
    started_at: int,
    rtmp_host: str | None = None,
):
    api = _batch_api()
    namespace = settings.K8S_NAMESPACE
    name = _job_name(stream_key)

    try:
        existing = api.read_namespaced_job(name=name, namespace=namespace)
        status = existing.status
        if not _is_terminal_job(status):
            return name
        api.delete_namespaced_job(
            name=name,
            namespace=namespace,
            propagation_policy="Background",
            grace_period_seconds=0,
        )
    except ApiException as e:
        if e.status != 404:
            raise

    body = _build_job(
        stream_key,
        user_id=user_id,
        started_at=started_at,
        rtmp_host=rtmp_host,
    )
    api.create_namespaced_job(namespace=namespace, body=body)
    return name


def stop_ffmpeg_container(container_name: str):
    api = _batch_api()
    try:
        api.delete_namespaced_job(
            name=container_name,
            namespace=settings.K8S_NAMESPACE,
            propagation_policy="Background",
            grace_period_seconds=0,
        )
    except ApiException as e:
        if e.status != 404:
            raise
