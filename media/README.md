# Media

`media/`는 media pipeline을 구성하는 runtime component source를 모아둔 디렉터리입니다.

| 경로 | 역할 |
|---|---|
| [onprem/](onprem) | 평시 On-Prem live streaming component |
| [aws-burst/](aws-burst) | AWS burst path용 media component |

배포 manifest는 [../onprem](../onprem), [../aws](../aws)에 분리되어 있습니다.
