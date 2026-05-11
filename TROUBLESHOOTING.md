# Troubleshooting

## 1. RTMP publish/pull path mismatch

### 증상

OBS publish는 성공했지만 ffmpeg가 stream을 읽지 못하는 경우가 있었습니다. stream key 인증은 통과했는데도 ffmpeg pull 대상이 실제 publish session이 붙은 nginx-rtmp Pod와 달라질 수 있었습니다.

### 원인

RTMP publish session은 OBS 연결을 받은 nginx-rtmp Pod에 붙습니다. 그런데 ffmpeg가 다시 Kubernetes Service 주소로 pull하면 Service load balancing 때문에 다른 nginx-rtmp Pod로 연결될 수 있습니다.

### 해결

stream-controller가 `on_publish` callback의 source IP를 읽고, ffmpeg Job 생성 시 해당 RTMP Pod IP를 `RTMP_HOST`로 전달했습니다.

Evidence:

- [media/onprem/stream-controller/app/api/rtmp.py](media/onprem/stream-controller/app/api/rtmp.py)
- [media/aws-burst/stream-controller/app/api/rtmp.py](media/aws-burst/stream-controller/app/api/rtmp.py)

## 2. Node-local HLS routing mismatch

### 증상

`index.m3u8`는 열리지만 player에서는 검정 화면이 나오거나 `.ts` 404가 섞였습니다. 새로고침하면 될 때도 있고 안 될 때도 있었습니다.

### 원인

ffmpeg는 특정 node-local storage에 HLS file을 생성했지만 viewer 요청은 임의의 nginx-hls Pod로 갈 수 있었습니다. Node A에 생성된 segment를 Node B의 nginx-hls에서 찾으면서 404가 발생했습니다.

### 해결

stream-controller가 ffmpeg Job이 배치된 node를 확인하고, 같은 node의 nginx-hls target을 Redis `hls:route:{stream_key}`에 저장했습니다. hls-router는 이 route state를 보고 정확한 nginx-hls target으로 proxy합니다.

Evidence:

- [media/onprem/stream-controller/app/services/ffmpeg.py](media/onprem/stream-controller/app/services/ffmpeg.py)
- [media/onprem/hls-router/app/main.py](media/onprem/hls-router/app/main.py)

## 3. Steering and burst control order

### 문제

AWS는 burst 실행 경로지만 실제 부하는 평시 경로인 On-Prem media line에서 먼저 쌓입니다. viewer steering보다 RTMP burst를 먼저 켜면 기존 viewer traffic이 계속 On-Prem HLS 경로를 압박할 수 있습니다.

### 해결

전환 순서를 아래처럼 고정했습니다.

1. On-Prem telemetry를 trigger 기준으로 사용
2. HLS steering으로 viewer traffic을 CDN으로 먼저 이동
3. 신규 RTMP session만 AWS burst로 이동
4. 복구 시에는 burst off 후 steering off

Evidence:

- [monitoring/prometheus/rules.example.yml](monitoring/prometheus/rules.example.yml)
- [aws/route53-lambda/hls-steering-lambda.py](aws/route53-lambda/hls-steering-lambda.py)
- [aws/route53-lambda/rtmp-burst-lambda.py](aws/route53-lambda/rtmp-burst-lambda.py)

## 4. Live/VOD cache separation

Live manifest는 계속 바뀌고, VOD manifest와 media segment는 상대적으로 길게 cache할 수 있습니다. 이 구조에서는 live HLS routing과 VOD playback path를 분리하고, VOD는 `{user_id}/{started_at}` 기반 경로로 정리했습니다.

Evidence:

- [media/onprem/stream-controller/app/services/vod_playlist.py](media/onprem/stream-controller/app/services/vod_playlist.py)
- [data-contracts/backend-integration/live-vod-query.example.py](data-contracts/backend-integration/live-vod-query.example.py)
