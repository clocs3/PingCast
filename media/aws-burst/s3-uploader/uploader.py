import logging
import mimetypes
import os
import time
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Dict, List, Tuple

import boto3
from botocore.exceptions import ClientError


def env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def endpoint_url(endpoint: str, secure: bool) -> str | None:
    cleaned = endpoint.strip()
    if not cleaned:
        return None
    if cleaned.startswith(("http://", "https://")):
        return cleaned
    scheme = "https" if secure else "http"
    return f"{scheme}://{cleaned}"


def build_s3_client(region: str):
    endpoint = endpoint_url(
        os.getenv("OBJECT_STORAGE_ENDPOINT", ""),
        env_bool("OBJECT_STORAGE_SECURE", True),
    )
    access_key = os.getenv("OBJECT_STORAGE_ACCESS_KEY", "").strip()
    secret_key = os.getenv("OBJECT_STORAGE_SECRET_KEY", "").strip()
    kwargs = {"region_name": region}
    if endpoint:
        kwargs["endpoint_url"] = endpoint
    if access_key and secret_key:
        kwargs["aws_access_key_id"] = access_key
        kwargs["aws_secret_access_key"] = secret_key
    return boto3.client("s3", **kwargs)


def ensure_bucket(client, bucket: str, region: str) -> None:
    try:
        client.head_bucket(Bucket=bucket)
        return
    except ClientError as exc:
        code = str(exc.response.get("Error", {}).get("Code", ""))
        if code not in {"404", "NoSuchBucket", "NotFound"}:
            raise

    args = {"Bucket": bucket}
    if region != "us-east-1":
        args["CreateBucketConfiguration"] = {"LocationConstraint": region}
    client.create_bucket(**args)


def configure_logging() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="[%(asctime)s] [uploader] %(levelname)s %(message)s",
    )


def mask_stream_key(stream_key: str) -> str:
    if not stream_key:
        return ""
    if len(stream_key) <= 8:
        return "***"
    return f"{stream_key[:4]}...{stream_key[-4:]}"


def is_ffmpeg_running() -> bool:
    if not env_bool("SHARE_PROCESS_NAMESPACE", True):
        return True

    try:
        for pid in os.listdir("/proc"):
            if not pid.isdigit():
                continue

            cmdline_path = f"/proc/{pid}/cmdline"
            try:
                with open(cmdline_path, "rb") as fh:
                    cmdline = fh.read().replace(b"\x00", b" ").strip().lower()
            except OSError:
                continue

            if b"ffmpeg" in cmdline and b"python /app/uploader.py" not in cmdline:
                return True
    except OSError:
        return True

    return False


def iter_target_files(root: str):
    for current_root, _, files in os.walk(root):
        for file_name in sorted(files):
            if not (
                file_name.endswith(".ts")
                or file_name.endswith(".m3u8")
                or file_name.endswith(".jpg")
            ):
                continue
            abs_path = os.path.join(current_root, file_name)
            if os.path.isfile(abs_path):
                rel_path = os.path.relpath(abs_path, root)
                yield abs_path, rel_path


def should_upload_immediately(rel_path: str) -> bool:
    lower = rel_path.lower()
    return lower.endswith(".m3u8")


def object_name(prefix: str, stream_key: str, rel_path: str, session_prefix: str) -> str:
    clean_prefix = prefix.strip("/")
    clean_session_prefix = session_prefix.strip("/")
    rel = rel_path.replace(os.sep, "/")
    if clean_session_prefix:
        return f"{clean_session_prefix}/{rel}"
    if clean_prefix:
        return f"{clean_prefix}/{stream_key}/{rel}"
    return f"{stream_key}/{rel}"


def object_names(
    prefix: str,
    stream_key: str,
    rel_path: str,
    session_prefix: str,
    live_prefix: str,
) -> List[str]:
    keys: List[str] = []
    session_key = object_name(prefix, stream_key, rel_path, session_prefix)
    if session_key:
        keys.append(session_key)

    clean_live_prefix = live_prefix.strip("/")
    if clean_live_prefix:
        rel = rel_path.replace(os.sep, "/")
        live_key = f"{clean_live_prefix}/{rel}"
        if live_key not in keys:
            keys.append(live_key)

    return keys


def upload_object(
    client,
    bucket: str,
    key: str,
    abs_path: str,
    signature: Tuple[int, int],
) -> Tuple[Tuple[int, int], str, str]:
    content_type = mimetypes.guess_type(abs_path)[0] or "application/octet-stream"

    with open(abs_path, "rb") as data:
        client.put_object(
            Bucket=bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
        )

    return signature, abs_path, key


def main() -> int:
    configure_logging()

    stream_key = os.getenv("STREAM_KEY", "").strip()
    bucket = os.getenv("OBJECT_STORAGE_BUCKET", "").strip()
    aws_region = os.getenv("AWS_REGION", "").strip() or "ap-northeast-2"

    if not stream_key:
        logging.error("STREAM_KEY is required")
        return 1
    if not bucket:
        logging.error("OBJECT_STORAGE_BUCKET is required")
        return 1

    root = os.getenv("HLS_OUTPUT_ROOT", "/hls")
    source_dir = os.path.join(root, stream_key)
    prefix = os.getenv("OBJECT_STORAGE_PREFIX", "").strip() or "hls"
    session_prefix = os.getenv("OBJECT_STORAGE_SESSION_PREFIX", "").strip()
    live_prefix = os.getenv("OBJECT_STORAGE_LIVE_PREFIX", "").strip()
    poll_interval = max(1, env_int("UPLOAD_POLL_SECONDS", 2))
    idle_exit_seconds = max(5, env_int("SIDECAR_IDLE_EXIT_SECONDS", 45))
    max_workers = max(1, env_int("UPLOAD_WORKERS", 4))
    client = build_s3_client(aws_region)
    if env_bool("OBJECT_STORAGE_AUTO_CREATE_BUCKET", False):
        ensure_bucket(client, bucket, aws_region)

    logging.info(
        "watching source_dir=%s bucket=%s prefix=%s session_prefix=%s live_prefix=%s poll=%ss",
        os.path.join(root, mask_stream_key(stream_key)),
        bucket,
        prefix,
        session_prefix,
        live_prefix,
        poll_interval,
    )

    while not os.path.isdir(source_dir):
        logging.info("waiting for source_dir=%s", source_dir)
        time.sleep(poll_interval)

    uploaded: Dict[str, Tuple[int, int]] = {}
    in_flight: Dict[str, Future] = {}
    pending_signature: Dict[str, Tuple[int, int]] = {}
    last_activity = time.time()

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        while True:
            for abs_path, rel_path in iter_target_files(source_dir):
                try:
                    stat = os.stat(abs_path)
                except OSError:
                    continue

                signature = (stat.st_mtime_ns, stat.st_size)
                keys = object_names(prefix, stream_key, rel_path, session_prefix, live_prefix)

                if should_upload_immediately(rel_path):
                    for key in keys:
                        artifact_id = f"{abs_path}|{key}"
                        if uploaded.get(artifact_id) == signature:
                            continue
                        existing_future = in_flight.get(artifact_id)
                        if existing_future and not existing_future.done():
                            continue
                        future = executor.submit(
                            upload_object,
                            client,
                            bucket,
                            key,
                            abs_path,
                            signature,
                        )
                        in_flight[artifact_id] = future
                    last_activity = time.time()
                    continue

                previous_seen = pending_signature.get(abs_path)
                pending_signature[abs_path] = signature
                if previous_seen != signature:
                    continue

                for key in keys:
                    artifact_id = f"{abs_path}|{key}"
                    if uploaded.get(artifact_id) == signature:
                        continue
                    existing_future = in_flight.get(artifact_id)
                    if existing_future and not existing_future.done():
                        continue
                    future = executor.submit(
                        upload_object,
                        client,
                        bucket,
                        key,
                        abs_path,
                        signature,
                    )
                    in_flight[artifact_id] = future
                last_activity = time.time()

            completed = [artifact_id for artifact_id, future in in_flight.items() if future.done()]
            for artifact_id in completed:
                future = in_flight.pop(artifact_id)
                try:
                    signature, abs_path, key = future.result()
                    uploaded[artifact_id] = signature
                    last_activity = time.time()
                    logging.info("uploaded %s", key)
                except Exception:
                    failed_path = artifact_id.split("|", 1)[0]
                    pending_signature.pop(failed_path, None)
                    logging.exception("upload failed for %s", artifact_id)

            idle_seconds = time.time() - last_activity
            if not in_flight and not is_ffmpeg_running() and idle_seconds >= idle_exit_seconds:
                logging.info("ffmpeg not running and idle for %.1fs, exiting", idle_seconds)
                break

            time.sleep(poll_interval)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
