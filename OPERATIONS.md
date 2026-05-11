# Operations Review

이 문서는 media pipeline을 운영 관점에서 확인할 때 보는 기준입니다.

## Review 기준

| 기준 | 이 repository에서 확인할 위치 |
|---|---|
| Scope | [README.md](README.md), [media/README.md](media/README.md) |
| Architecture trade-off | [diagrams/](diagrams), [TROUBLESHOOTING.md](TROUBLESHOOTING.md) |
| Deploy path | [ci-cd/](ci-cd), [gitops/](gitops) |
| Runtime state | [data-contracts/redis/keyspace.md](data-contracts/redis/keyspace.md) |
| Alert/metric | [monitoring/prometheus/rules.example.yml](monitoring/prometheus/rules.example.yml), [monitoring/grafana/dashboards](monitoring/grafana/dashboards) |
| Security boundary | [SECURITY.md](SECURITY.md), [SANITIZATION.md](SANITIZATION.md) |

## 핵심 운영 지표

| 영역 | 주요 지표 | 보는 이유 |
|---|---|---|
| RTMP ingest | `active_publishers`, nginx-rtmp pod/network metric | publisher 증가와 ingest 장애 확인 |
| ffmpeg | `ffmpeg_pending_streams`, `ffmpeg_start_failures_total`, ffmpeg pod phase | transcoding capacity와 startup failure 확인 |
| HLS delivery | `hls_route_ready_streams`, `hls_route_error_streams`, nginx-hls/hls-router pod metric | node-local routing 실패와 viewer 404 확인 |
| Steering/Burst | `control_steering_enabled`, `control_burst_enabled`, transition log | 전환 순서와 현재 traffic path 확인 |
| Storage/VOD | S3 object count, uploader log, VOD metadata write | archive/VOD 생성 누락 확인 |

## 장애 대응 흐름

### HLS 404 또는 검정 화면

1. `hls_route_error_streams`와 hls-router log를 확인합니다.
2. `live:stream:{stream_key}`의 `container_name`, `hls_route_target`, `hls_route_status`를 확인합니다.
3. ffmpeg Job pod node와 같은 node에 `nginx-hls` DaemonSet pod가 있는지 확인합니다.
4. route가 틀리면 stream-controller reconcile loop와 Redis `hls:route:{stream_key}` TTL을 확인합니다.

### ffmpeg pending 증가

1. `ffmpeg_pending_streams`와 ffmpeg Job pod phase를 확인합니다.
2. On-Prem HLS node CPU/memory, taint/toleration, nodeSelector를 확인합니다.
3. pending이 지속되면 Steering On 후 Burst On 순서로 신규 부하를 AWS로 넘깁니다.

### Steering/Burst 전환 실패

1. Alertmanager webhook delivery log와 Lambda response code를 확인합니다.
2. Redis `control:transition:lock`, `control:steering:enabled`, `control:burst:enabled`, `control:meta`를 확인합니다.
3. `burst_on`은 `steering_on` 이후에만 허용하고, `steering_off`는 `burst_off` 이후에만 허용합니다.
4. cooldown 때문에 거절된 경우는 실패가 아니라 기대한 제어 상태로 봅니다.

### VOD 누락

1. s3-uploader log에서 upload failure와 idle exit timing을 확인합니다.
2. S3 prefix `{user_id}/{started_at}` 아래 `.ts`, `index.m3u8`, `vod.m3u8`, `thumbnail.jpg` 존재 여부를 확인합니다.
3. MongoDB `user_vods`에서 `{user_id, started_at}` 기준 VOD document에 `vod_object_key`, `vod_path`, `thumbnail_path`가 기록됐는지 확인합니다.

## 검증 범위

이 public repository에서 자동 확인한 범위는 아래와 같습니다.

- Python syntax parse
- YAML/JSON syntax parse
- shell script syntax check
- Dockerfile `COPY` source 존재 확인
- Kustomize resource reference 확인
- Markdown link 확인
- secret/key pattern scan

실제 cluster 배포, Route53 변경, S3 upload, CloudFront cache behavior, OBS e2e streaming test는 sanitized repository만으로 재현하지 않습니다. 이 부분은 포트폴리오의 screenshot, diagram, 실행 기록으로 보완합니다.

## Production 보강 후보

| 항목 | 이유 |
|---|---|
| CloudFront/S3 IaC | live/VOD cache policy와 origin policy를 코드로 검증 가능하게 하기 위해 |
| PodSecurity/admission policy | hostPath, ffmpeg, nginx-rtmp 권한을 cluster policy로 제한하기 위해 |
| digest-pinned image | 동일 tag 재빌드와 supply chain risk를 줄이기 위해 |
| e2e smoke test | RTMP publish부터 HLS/VOD 확인까지 release gate로 묶기 위해 |
| load test baseline | steering/burst threshold를 경험값이 아니라 측정값으로 방어하기 위해 |
