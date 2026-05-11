# Security Note

공개 repository 기준으로 제거하거나 example 값으로 치환한 항목입니다.

| 항목 | 처리 기준 |
|---|---|
| AWS account/credential | account ID, access key, secret key 제거 |
| Kubernetes Secret | 실제 값 대신 example manifest만 유지 |
| Registry credential | Harbor/GitLab token 제거 |
| Lambda URL/token | environment variable 또는 placeholder로 치환 |
| Internal endpoint | private IP, domain, bastion 정보 제거 |

Production hardening 후보는 아래 항목을 우선순위로 봅니다.

- IRSA 기반 Pod 단위 AWS 권한 분리
- Security Group/NACL 최소 허용
- S3 bucket policy와 CloudFront OAC 적용
- Kubernetes Secret 외부 secret manager 연동
- image digest pinning과 vulnerability scan gate 적용
