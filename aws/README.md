# AWS

`aws/`는 AWS burst path와 traffic control 구성을 모아둔 디렉터리입니다.

| 경로 | 역할 |
|---|---|
| [eks/](eks) | AWS EKS media workload와 platform manifest |
| [route53-lambda/](route53-lambda) | HLS steering, RTMP burst 제어 Lambda 예시 |

AWS 경로는 평시 media serving 경로가 아니라, 부하 증가 시 신규 RTMP session과 CDN playback을 처리하는 확장 경로를 보여줍니다.
