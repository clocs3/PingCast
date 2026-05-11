# Route53 Lambda

`aws/route53-lambda/`는 Route53 weighted record를 제어하는 Lambda 예시를 모아둔 디렉터리입니다.

| 파일 | 역할 |
|---|---|
| `hls-steering-lambda.py` | HLS viewer path를 On-Prem/CDN 사이에서 전환 |
| `rtmp-burst-lambda.py` | 신규 RTMP publish path를 On-Prem/AWS 사이에서 전환 |
| `env.example` | Lambda environment variable 예시 |
| `requirements.txt` | Lambda runtime dependency |

전환 순서와 운영 기준은 [../../OPERATIONS.md](../../OPERATIONS.md), 문제 해결 기록은 [../../TROUBLESHOOTING.md](../../TROUBLESHOOTING.md)를 참고합니다.
