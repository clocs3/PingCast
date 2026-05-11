# AWS EKS Media

`aws/eks/media/`는 AWS burst media line의 Kubernetes manifest를 정리한 디렉터리입니다.

| 경로/파일 | 역할 |
|---|---|
| `base/namespace.yaml` | AWS media namespace |
| `base/workloads.yaml` | nginx-rtmp, stream-controller, ffmpeg/s3-uploader Job 관련 workload |
| `base/kustomization.yaml` | base manifest entrypoint |
| `overlays/kustomization.yaml` | image tag patch 예시 |

AWS burst line은 `nginx-hls`, `hls-router`를 두지 않고 S3/CloudFront playback 경로를 사용합니다.
