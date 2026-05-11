import io
import re
from typing import List

import boto3

from app.core.config import settings

_SEGMENT_RE = re.compile(r"seg_(\d+)\.ts$")


def _endpoint_url() -> str | None:
    endpoint = settings.OBJECT_STORAGE_ENDPOINT.strip()
    if not endpoint:
        return None
    if endpoint.startswith(("http://", "https://")):
        return endpoint
    scheme = "https" if settings.OBJECT_STORAGE_SECURE else "http"
    return f"{scheme}://{endpoint}"


def _s3_client():
    kwargs = {"region_name": settings.AWS_REGION}
    endpoint = _endpoint_url()
    if endpoint:
        kwargs["endpoint_url"] = endpoint
    if settings.OBJECT_STORAGE_ACCESS_KEY and settings.OBJECT_STORAGE_SECRET_KEY:
        kwargs["aws_access_key_id"] = settings.OBJECT_STORAGE_ACCESS_KEY
        kwargs["aws_secret_access_key"] = settings.OBJECT_STORAGE_SECRET_KEY
    return boto3.client("s3", **kwargs)


def _sorted_ts_keys(object_keys: List[str]) -> List[str]:
    def sort_key(key: str):
        file_name = key.rsplit("/", 1)[-1]
        matched = _SEGMENT_RE.match(file_name)
        if matched:
            return (0, int(matched.group(1)))
        return (1, file_name)

    return sorted(object_keys, key=sort_key)


def build_and_upload_vod_playlist(vod_prefix: str) -> str:
    prefix = f"{vod_prefix.strip('/')}/"
    client = _s3_client()
    paginator = client.get_paginator("list_objects_v2")
    ts_keys = []
    for page in paginator.paginate(Bucket=settings.OBJECT_STORAGE_BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith(".ts"):
                ts_keys.append(key)
    ts_keys = _sorted_ts_keys(ts_keys)

    if not ts_keys:
        raise ValueError(f"no ts segments found at prefix={vod_prefix}")

    lines = [
        "#EXTM3U",
        "#EXT-X-VERSION:3",
        f"#EXT-X-TARGETDURATION:{settings.HLS_SEGMENT_SECONDS}",
        "#EXT-X-MEDIA-SEQUENCE:0",
    ]

    for key in ts_keys:
        rel_name = key[len(prefix) :]
        lines.append(f"#EXTINF:{float(settings.HLS_SEGMENT_SECONDS):.3f},")
        lines.append(rel_name)

    lines.append("#EXT-X-ENDLIST")
    payload = ("\n".join(lines) + "\n").encode("utf-8")

    object_name = f"{vod_prefix.strip('/')}/vod.m3u8"
    client.put_object(
        Bucket=settings.OBJECT_STORAGE_BUCKET,
        Key=object_name,
        Body=io.BytesIO(payload),
        ContentType="application/vnd.apple.mpegurl",
    )

    return object_name
