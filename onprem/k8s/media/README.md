# On-Prem K8s Media

`onprem/k8s/media/`는 On-Prem Kubernetes cluster에 media line을 배치하기 위한 manifest 디렉터리입니다.

| 경로/파일 | 역할 |
|---|---|
| `base/namespace.yaml` | On-Prem media namespace |
| `base/workloads.yaml` | nginx-rtmp, stream-controller, nginx-hls, hls-router, ffmpeg Job 관련 권한과 Service |
| `base/kustomization.yaml` | base manifest entrypoint |
| `overlays/kustomization.yaml` | image tag patch 예시 |

component source는 [../../../media/onprem](../../../media/onprem), 운영 기준은 [../../../OPERATIONS.md](../../../OPERATIONS.md)를 참고합니다.
