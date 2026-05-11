# Sanitization Guide

원본 구현 파일을 public portfolio/evidence repository로 옮길 때 적용한 치환 기준입니다.

## Replacement Rules

| 원본 값 | 공개용 값 |
|---|---|
| 실제 domain | `example.com` 또는 `*.example.com` |
| AWS account ID | `123456789012` |
| internal IP/host | `*.internal.example` 또는 문서용 reserved range |
| 실제 ARN | `arn:aws:iam::123456789012:role/example-role` 형태의 placeholder |
| Lambda Function URL | `<REDACTED_LAMBDA_URL>` 또는 environment variable |
| database password | `${POSTGRES_PASSWORD}` |
| secret/token/private key | 제거하거나 명확한 placeholder로 치환 |
| runtime archive/package | public tree에서 제거 |

## File Naming

- 실제 운영 원본은 account-specific data가 있으면 그대로 공개하지 않습니다.
- 공개 예시는 `*.example.yaml`, `*.example.yml`, `*.example.json`, `.env.example` 형식을 사용합니다.
- source code는 secret, internal address, unsafe default를 제거한 경우에만 원래 filename을 유지합니다.

## Review Checklist

- 실제 IP, domain, account ID, bucket name, ARN, Lambda URL이 남아 있지 않은지 확인합니다.
- private key, access key, OAuth secret, registry credential, Kubernetes Secret value가 남아 있지 않은지 확인합니다.
- local database backup, Jenkins home, Harbor data, zip/tgz Lambda package, generated binary artifact를 포함하지 않습니다.
- README와 diagram의 용어가 implementation file의 sanitized vocabulary와 맞는지 확인합니다.
- placeholder 값은 reviewer가 production 값으로 오해하지 않도록 명확하게 표시합니다.
