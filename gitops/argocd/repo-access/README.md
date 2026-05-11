# Argo CD Repository Access

`gitops/argocd/repo-access/`는 Argo CD repository 접근 설정의 sanitized example을 둔 디렉터리입니다.

| 파일 | 역할 |
|---|---|
| `repo-secret.example.yaml` | Git repository credential Secret 예시 |
| `ssh-known-hosts.example.yaml` | Git server known_hosts 예시 |

실제 private SSH key, registry credential, private GitLab URL은 포함하지 않습니다.
