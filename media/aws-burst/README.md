# AWS Burst Media

`media/aws-burst/`는 AWS burst path에서 사용하는 media component source 디렉터리입니다.

| 경로 | 역할 |
|---|---|
| `nginx-rtmp/` | AWS RTMP ingest |
| `stream-controller/` | AWS origin live state와 ffmpeg Job orchestration |
| `ffmpeg/` | transient HLS artifact 생성 |
| `s3-uploader/` | S3 upload와 CloudFront playback 경로 연결 |

AWS burst line은 `nginx-hls`, `hls-router`를 포함하지 않습니다. 관련 manifest는 [../../aws/eks/media](../../aws/eks/media)를 참고합니다.
