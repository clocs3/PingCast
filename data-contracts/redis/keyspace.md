# Redis Keyspace

Redis is used as the real-time control/state store between the web backend,
stream-controller, hls-router, Prometheus metrics, and Route53 control Lambdas.

| Key | Type | Owner | Purpose |
|---|---|---|---|
| `cache:stream_key:{stream_key_hash}` | string | stream-controller | Short-lived stream key authentication cache. |
| `security:fail:{stream_key_hash}` | string | stream-controller | Temporary failed publish counter for throttling invalid stream keys. |
| `lock:ffmpeg:{stream_key}` | string | stream-controller | Prevents duplicate ffmpeg Jobs per broadcast. |
| `live:stream:{stream_key}` | hash | stream-controller | Live session state: `user_id`, `status`, `origin_cluster`, `started_at`, `vod_prefix`, route metadata. |
| `pending:done:{stream_key}` | string | stream-controller | Disconnect grace marker before finalizing a stream. |
| `done:vod:{stream_key}:{started_at}` | string | stream-controller | Idempotency key for VOD finalization. |
| `hls:route:{stream_key}` | string | stream-controller, hls-router | Node-local HLS target, such as `<node-internal-ip>:8081`. |
| `hls:session:{user_id}:{started_at}` | string | stream-controller, hls-router | Maps public playback path to the current stream key. |
| `control:steering:enabled` | string bool | Lambda | Viewer steering state. |
| `control:burst:enabled` | string bool | Lambda | RTMP burst state. |
| `control:transition:lock` | string | Lambda | Cross-Lambda transition lock. |
| `control:meta` | hash | Lambda, stream-controller | Last transition action/result timestamps for dashboards and logs. |

The public playback path should prefer `{user_id}/{started_at}` over exposing
the raw stream key.
