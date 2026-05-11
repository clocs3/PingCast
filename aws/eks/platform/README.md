# AWS EKS Platform

`aws/eks/platform/`은 media workload와 분리된 EKS platform 구성 예시를 모아둔 디렉터리입니다.

| 경로 | 역할 |
|---|---|
| `karpenter/` | general/ffmpeg NodePool, EC2NodeClass, warm capacity placeholder |
| `media-irsa/` | S3 upload 권한을 위한 IRSA policy/trust example |

세부 운영 판단은 [../../../OPERATIONS.md](../../../OPERATIONS.md)에 정리했습니다.
