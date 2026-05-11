import base64
import hmac
import json
import os
import time
import uuid
from typing import Any

import boto3
import redis

STEERING_ENABLED_KEY = "control:steering:enabled"
BURST_ENABLED_KEY = "control:burst:enabled"
TRANSITION_LOCK_KEY = "control:transition:lock"
CONTROL_META_KEY = "control:meta"
LOCK_RELEASE_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
  return redis.call("del", KEYS[1])
end
return 0
"""

SUPPORTED_ACTIONS = {"steering_on", "steering_off"}
NON_FATAL_ERROR_PATTERNS = (
    "cooldown active",
    "blocked while burst is enabled",
    "blocked until steering is enabled",
    "unsupported action",
)


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return int(value)


def _redis_client() -> redis.Redis:
    return redis.Redis(
        host=os.environ["REDIS_HOST"],
        port=_env_int("REDIS_PORT", 6379),
        db=_env_int("REDIS_DB", 0),
        password=os.getenv("REDIS_PASSWORD"),
        ssl=_env_bool("REDIS_SSL", False),
        decode_responses=True,
    )


def _route53_client():
    return boto3.client("route53")


def _normalize_dns_name(name: str) -> str:
    return name if name.endswith(".") else f"{name}."


def _meta_updates(
    action: str,
    source: str,
    result: str,
    reason: str | None = None,
    change_id: str | None = None,
) -> dict[str, str]:
    payload = {
        "last_action": action,
        "last_action_at": str(int(time.time())),
        "last_action_source": source,
        "last_result": result,
    }
    if reason:
        payload["last_reason"] = reason
    if change_id:
        payload["last_route53_change_id"] = change_id
    return payload


def _redis_bool(client: redis.Redis, key: str) -> bool | None:
    value = client.get(key)
    if value is None:
        return None
    return value.strip().lower() == "true"


def _parse_event(event: Any) -> dict[str, Any]:
    if not isinstance(event, dict):
        return {}

    body = event.get("body")
    if isinstance(body, str) and body.strip():
        payload = body
        if event.get("isBase64Encoded"):
            payload = base64.b64decode(payload).decode("utf-8")
        parsed = json.loads(payload)
        if isinstance(parsed, dict):
            return parsed

    return event


def _ensure_authorized(raw_event: dict[str, Any]) -> None:
    expected_token = os.getenv("WEBHOOK_BEARER_TOKEN", "").strip()
    if not expected_token:
        raise PermissionError("webhook token is not configured")

    headers = raw_event.get("headers") or {}
    auth_header = ""
    for key, value in headers.items():
        if key.lower() == "authorization":
            auth_header = str(value)
            break

    expected_header = f"Bearer {expected_token}"
    if not hmac.compare_digest(auth_header, expected_header):
        raise PermissionError("unauthorized webhook request")


def _get_action(event: dict[str, Any]) -> tuple[str, str, str | None]:
    action = event.get("action")
    if action in SUPPORTED_ACTIONS:
        return action, "manual", event.get("reason")

    for alert in event.get("alerts") or []:
        labels = alert.get("labels") or {}
        action = labels.get("control_action")
        if action in SUPPORTED_ACTIONS:
            annotations = alert.get("annotations") or {}
            reason = annotations.get("summary") or annotations.get("description")
            return action, "alertmanager", reason

    raise ValueError("no supported steering action found in event")


def _check_cooldown(client: redis.Redis, action: str) -> None:
    cooldown = _env_int("STEERING_COOLDOWN_SECONDS", 900)
    if cooldown <= 0:
        return
    last_action = client.hget(CONTROL_META_KEY, "last_steering_action")
    last_action_at = client.hget(CONTROL_META_KEY, "last_steering_action_at")
    if last_action != action or not last_action_at:
        return
    elapsed = int(time.time()) - int(last_action_at)
    if elapsed < cooldown:
        raise RuntimeError(f"steering cooldown active for action={action}, remaining={cooldown - elapsed}s")


def _is_non_fatal_error(exc: Exception) -> bool:
    message = str(exc)
    return any(pattern in message for pattern in NON_FATAL_ERROR_PATTERNS)


def _ensure_action_allowed(client: redis.Redis, action: str) -> None:
    burst_enabled = _redis_bool(client, BURST_ENABLED_KEY)
    if action == "steering_off" and burst_enabled:
        raise RuntimeError("steering_off is blocked while burst is enabled")


def _acquire_lock(client: redis.Redis, action: str) -> str:
    ttl = _env_int("CONTROL_LOCK_TTL_SECONDS", 60)
    token = f"{action}:{int(time.time())}:{uuid.uuid4()}"
    acquired = client.set(TRANSITION_LOCK_KEY, token, nx=True, ex=ttl)
    if not acquired:
        existing = client.get(TRANSITION_LOCK_KEY)
        raise RuntimeError(f"transition already in progress: {existing}")
    return token


def _release_lock(client: redis.Redis, token: str) -> None:
    client.eval(LOCK_RELEASE_SCRIPT, 1, TRANSITION_LOCK_KEY, token)


def _set_weighted_hls_records(route53_client, steering_enabled: bool) -> str:
    hosted_zone_id = os.environ["HOSTED_ZONE_ID"]
    record_name = _normalize_dns_name(os.environ["HLS_RECORD_NAME"])

    onprem_idle_weight = _env_int("HLS_ONPREM_WEIGHT_DEFAULT", 100)
    onprem_active_weight = _env_int("HLS_ONPREM_WEIGHT_ACTIVE", 0)
    cdn_idle_weight = _env_int("CDN_WEIGHT_IDLE", 0)
    cdn_active_weight = _env_int("CDN_WEIGHT_ACTIVE", 100)
    onprem_weight = onprem_active_weight if steering_enabled else onprem_idle_weight
    cdn_weight = cdn_active_weight if steering_enabled else cdn_idle_weight

    batch = {
        "Comment": f"hls steering {'on' if steering_enabled else 'off'}",
        "Changes": [
            {
                "Action": "UPSERT",
                "ResourceRecordSet": {
                    "Name": record_name,
                    "Type": "A",
                    "SetIdentifier": os.environ["HLS_ONPREM_SET_ID"],
                    "Weight": onprem_weight,
                    "AliasTarget": {
                        "HostedZoneId": os.environ["HLS_ONPREM_ALIAS_HOSTED_ZONE_ID"],
                        "DNSName": _normalize_dns_name(os.environ["HLS_ONPREM_ALIAS_DNS_NAME"]),
                        "EvaluateTargetHealth": True,
                    },
                },
            },
            {
                "Action": "UPSERT",
                "ResourceRecordSet": {
                    "Name": record_name,
                    "Type": "A",
                    "SetIdentifier": os.environ["CDN_SET_ID"],
                    "Weight": cdn_weight,
                    "AliasTarget": {
                        "HostedZoneId": os.environ["CDN_ALIAS_HOSTED_ZONE_ID"],
                        "DNSName": _normalize_dns_name(os.environ["CDN_ALIAS_DNS_NAME"]),
                        "EvaluateTargetHealth": False,
                    },
                },
            },
        ],
    }

    response = route53_client.change_resource_record_sets(
        HostedZoneId=hosted_zone_id,
        ChangeBatch=batch,
    )
    return response["ChangeInfo"]["Id"]


def _handle_steering(
    client: redis.Redis,
    route53_client,
    enabled: bool,
    action: str,
    source: str,
    reason: str | None,
) -> dict[str, Any]:
    now = str(int(time.time()))
    change_id = _set_weighted_hls_records(route53_client, steering_enabled=enabled)
    client.set(STEERING_ENABLED_KEY, "true" if enabled else "false")
    steering_event_field = "last_steering_trigger_at" if enabled else "last_steering_recover_at"
    client.hset(
        CONTROL_META_KEY,
        mapping={
            **_meta_updates(action=action, source=source, result="success", reason=reason, change_id=change_id),
            "steering_enabled": "true" if enabled else "false",
            "last_steering_action": action,
            "last_steering_action_at": now,
            steering_event_field: now,
        },
    )
    return {
        "ok": True,
        "action": action,
        "steering_enabled": enabled,
        "route53_change_id": change_id,
    }


def lambda_handler(event, context):
    action = "unknown"
    source = "unknown"
    lock_token = ""

    try:
        if isinstance(event, dict):
            _ensure_authorized(event)
        parsed_event = _parse_event(event)
        action, source, reason = _get_action(parsed_event)
    except PermissionError as exc:
        return {
            "statusCode": 401,
            "body": json.dumps({"ok": False, "error": str(exc)}),
        }
    except Exception as exc:
        return {
            "statusCode": 400,
            "body": json.dumps({"ok": False, "error": str(exc)}),
        }

    client = _redis_client()
    route53_client = _route53_client()

    try:
        lock_token = _acquire_lock(client, action)
        _check_cooldown(client, action)
        _ensure_action_allowed(client, action)

        if action == "steering_on":
            result = _handle_steering(client, route53_client, enabled=True, action=action, source=source, reason=reason)
        elif action == "steering_off":
            result = _handle_steering(client, route53_client, enabled=False, action=action, source=source, reason=reason)
        else:
            raise RuntimeError(f"unsupported action: {action}")

        return {
            "statusCode": 200,
            "body": json.dumps(result),
        }
    except Exception as exc:
        client.hset(
            CONTROL_META_KEY,
            mapping=_meta_updates(action=action, source=source, result="failed", reason=str(exc)),
        )
        status_code = 200 if _is_non_fatal_error(exc) else 500
        return {
            "statusCode": status_code,
            "body": json.dumps({"ok": False, "action": action, "error": str(exc)}),
        }
    finally:
        if lock_token:
            _release_lock(client, lock_token)
