# Monitoring

`monitoring/`은 media system의 metric, log, trace, alert 예시를 모아둔 디렉터리입니다.

| 경로 | 역할 |
|---|---|
| `prometheus/` | scrape config와 alert rule 예시 |
| `alertmanager/` | Route53 Lambda webhook receiver 예시 |
| `alloy/` | On-Prem agent와 central gateway 예시 |
| `grafana/dashboards/` | media, steering, burst dashboard JSON |
| `grafana/screenshots/` | dashboard 동작 증거용 캡처 |
| `loki/` | log backend example |
| `tempo/` | trace backend example |

운영 지표와 장애 대응 흐름은 [../OPERATIONS.md](../OPERATIONS.md)를 참고합니다.
