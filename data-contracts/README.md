# Data Contracts

`data-contracts/`는 media pipeline과 backend 사이의 데이터 계약을 정리한 디렉터리입니다.

| 경로/파일 | 역할 |
|---|---|
| `postgres/init.sql` | user, profile, follow, game, stream key hash contract |
| `mongodb/init.js` | VOD metadata collection/index contract |
| `redis/keyspace.md` | live/session/route/control state keyspace |
| `backend-integration/` | backend API 연동 예시 |

구현 세부 판단과 보안 기준은 [../SECURITY.md](../SECURITY.md), 운영 기준은 [../OPERATIONS.md](../OPERATIONS.md)를 참고합니다.
