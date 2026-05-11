# Pingcast
# Hybrid Streaming Platform

스트리밍 플랫폼의 media infrastructure 구현 증거를 정리한 repository입니다.

README는 repository 구조를 빠르게 파악하기 위한 안내용으로 사용합니다.

## Directory Guide

| 경로 | 역할 |
|---|---|
| [media/](media) | On-Prem/AWS media component source |
| [onprem/](onprem) | On-Prem Kubernetes media workload manifest |
| [aws/](aws) | AWS EKS burst path, Karpenter, IRSA, Route53 Lambda |
| [data-contracts/](data-contracts) | PostgreSQL, MongoDB, Redis contract와 backend integration 예시 |
| [ci-cd/](ci-cd) | Jenkins, GitLab, Harbor, Trivy 기반 CI/CD 예시 |
| [gitops/](gitops) | Argo CD Application/AppProject 예시 |
| [monitoring/](monitoring) | Prometheus, Alertmanager, Alloy, Grafana 예시 |
| [diagrams/](diagrams) | Architecture diagram과 Mermaid source |
| [screenshots/](screenshots) | 실행 화면 증거를 둘 위치 |

## Reference Docs

| 문서 | 역할 |
|---|---|
| [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | 핵심 문제 해결 기록 |
| [OPERATIONS.md](OPERATIONS.md) | 운영 지표, 장애 대응 흐름, 검증 범위 |
| [SECURITY.md](SECURITY.md) | 공개용 보안 정리와 production hardening note |
| [SANITIZATION.md](SANITIZATION.md) | 공개 repository 정리 기준 |

## Public Repository Note

실제 domain, account ID, private key, registry credential, internal IP, Lambda URL, OAuth secret은 제거하거나 example 값으로 치환했습니다.
