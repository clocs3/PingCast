# Diagrams

`diagrams/`는 repository를 열었을 때 전체 구조를 빠르게 파악하기 위한 그림 자료 디렉터리입니다.

| 파일 | 역할 |
|---|---|
| `overall-hybrid-architecture.png` | On-Prem + AWS hybrid 전체 구조 |
| `onprem-media-architecture.png` | 평시 On-Prem media line |
| `aws-burst-architecture.png` | AWS burst, S3, CDN 경로 |
| `media-pipeline-flow.mmd` | RTMP publish부터 VOD metadata까지의 lifecycle |
| `hls-router-flow.mmd` | node-local HLS route resolution |
| `steering-bursting-state-flow.mmd` | steering/burst state transition order |

diagram에는 실제 IP, domain, account ID, private URL, secret name을 넣지 않습니다.
