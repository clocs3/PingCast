# Argo CD

`gitops/argocd/`는 Argo CD 배포 모델을 확인하기 위한 manifest 디렉터리입니다.

| 경로 | 역할 |
|---|---|
| `projects/` | AWS와 On-Prem AppProject example |
| `root/` | App-of-Apps root Application example |
| `applications/` | media, monitoring, platform Application example |
| `repo-access/` | repository credential 관련 sanitized example |

CI/CD 흐름은 [../../ci-cd](../../ci-cd), 운영 기준은 [../../OPERATIONS.md](../../OPERATIONS.md)를 참고합니다.
