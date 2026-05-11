FROM jrottenberg/ffmpeg:8.0-alpine

USER root
WORKDIR /app

COPY entrypoint.sh /app/entrypoint.sh

RUN sed -i 's/\r$//' /app/entrypoint.sh \
 && chmod +x /app/entrypoint.sh \
 && mkdir -p /hls

ENTRYPOINT ["/bin/sh", "/app/entrypoint.sh"]
