# CI/CD

`ci-cd/`는 media component의 build, scan, registry push, GitOps repo update 흐름을 보여주는 디렉터리입니다.

| 경로 | 역할 |
|---|---|
| `pipelines/` | On-Prem/AWS media image build와 GitOps update Jenkinsfile |
| `jenkins/` | Jenkins controller image와 compose 예시 |
| `gitlab/` | GitLab compose 예시 |
| `harbor/` | Harbor registry 정리 안내 |

운영 관점의 검증 범위는 [../OPERATIONS.md](../OPERATIONS.md)를 참고합니다.
