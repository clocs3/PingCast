# On-Prem Media

`media/onprem/`은 평시 On-Prem media line에서 사용하는 component source 디렉터리입니다.

| 경로 | 역할 |
|---|---|
| `nginx-rtmp/` | RTMP ingest와 stream-controller callback |
| `stream-controller/` | stream key validation, live state, ffmpeg Job orchestration |
| `ffmpeg/` | RTMP pull과 HLS segment 생성 |
| `nginx-hls/` | node-local HLS static serving |
| `hls-router/` | Redis route 기반 HLS proxy |
| `s3-uploader/` | HLS/VOD artifact upload |

관련 Kubernetes manifest는 [../../onprem/k8s/media](../../onprem/k8s/media)를 참고합니다.
