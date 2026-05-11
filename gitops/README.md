# GitOps

`gitops/`는 Argo CD가 어떤 manifest를 watch/sync했는지 보여주는 디렉터리입니다.

| 경로 | 역할 |
|---|---|
| [argocd/](argocd) | AppProject, Application, repository access example |

실제 workload manifest는 [../onprem/k8s](../onprem/k8s), [../aws/eks](../aws/eks)에 두고, 이 디렉터리에는 Argo CD 관련 파일만 모았습니다.
