#!/bin/sh
set -eu

if [ -z "${STREAM_KEY:-}" ]; then
  echo "[entrypoint] STREAM_KEY missing"
  exit 1
fi

RTMP_HOST="${RTMP_HOST:-nginx-rtmp.ns-media.svc.cluster.local}"
RTMP_PORT="${RTMP_PORT:-1935}"
RTMP_APP="${RTMP_APP:-live}"
HLS_OUTPUT_ROOT="${HLS_OUTPUT_ROOT:-/hls}"
HLS_CLEANUP_ON_START="${HLS_CLEANUP_ON_START:-true}"
HLS_CLEANUP_ON_EXIT="${HLS_CLEANUP_ON_EXIT:-true}"
INPUT_CONNECT_RETRY_SECONDS="${INPUT_CONNECT_RETRY_SECONDS:-3}"
INPUT_CONNECT_MAX_RETRIES="${INPUT_CONNECT_MAX_RETRIES:-20}"

OUT="${HLS_OUTPUT_ROOT}/${STREAM_KEY}"
INPUT_URL="rtmp://${RTMP_HOST}:${RTMP_PORT}/${RTMP_APP}/${STREAM_KEY}"

mask_stream_key() {
  key="$1"
  len=${#key}
  if [ "$len" -le 8 ]; then
    printf '%s' '***'
    return
  fi
  prefix=$(printf '%s' "$key" | cut -c 1-4)
  suffix_start=$((len - 3))
  suffix=$(printf '%s' "$key" | cut -c "$suffix_start-$len")
  printf '%s...%s' "$prefix" "$suffix"
}

cleanup() {
  if [ "$HLS_CLEANUP_ON_EXIT" = "true" ] || [ "$HLS_CLEANUP_ON_EXIT" = "1" ]; then
    echo "[entrypoint] cleanup on exit: removing $OUT"
    rm -rf "$OUT" || true
  fi
}

trap cleanup EXIT INT TERM

if [ "$HLS_CLEANUP_ON_START" = "true" ] || [ "$HLS_CLEANUP_ON_START" = "1" ]; then
  echo "[entrypoint] cleanup on start: removing $OUT"
  rm -rf "$OUT" || true
fi

mkdir -p "$OUT"

MASKED_STREAM_KEY=$(mask_stream_key "$STREAM_KEY")
echo "[entrypoint] STREAM_KEY=$MASKED_STREAM_KEY"
echo "[entrypoint] INPUT_URL=rtmp://${RTMP_HOST}:${RTMP_PORT}/${RTMP_APP}/${MASKED_STREAM_KEY}"
echo "[entrypoint] OUT=${HLS_OUTPUT_ROOT}/${MASKED_STREAM_KEY}"
echo "[entrypoint] INPUT_CONNECT_RETRY_SECONDS=$INPUT_CONNECT_RETRY_SECONDS"
echo "[entrypoint] INPUT_CONNECT_MAX_RETRIES=$INPUT_CONNECT_MAX_RETRIES"
ls -al "$HLS_OUTPUT_ROOT" || true
ls -al "$OUT" || true

attempt=0
while :; do
  attempt=$((attempt+1))
  echo "[entrypoint] starting ffmpeg (attempt=$attempt)"

  if ffmpeg -hide_banner -loglevel info \
    -i "$INPUT_URL" \
    -map 0:v:0 -map 0:a:0? \
    -c:v libx264 \
    -preset ultrafast \
    -tune zerolatency \
    -pix_fmt yuv420p \
    -profile:v baseline \
    -level 3.1 \
    -b:v 1800k \
    -maxrate 2200k \
    -bufsize 3600k \
    -g 180 \
    -keyint_min 180 \
    -sc_threshold 0 \
    -force_key_frames "expr:gte(t,n_forced*6)" \
    -c:a aac \
    -b:a 64k \
    -ac 2 \
    -ar 48000 \
    -f hls \
      -hls_time 6 \
      -hls_list_size 2 \
      -hls_delete_threshold 10 \
      -hls_flags delete_segments+append_list+independent_segments \
      -hls_segment_filename "${OUT}/seg_%03d.ts" \
      "${OUT}/index.m3u8" \
    -map 0:v \
    -vf "fps=1/10" \
    -update 1 \
    -y "${OUT}/thumbnail.jpg"; then
    rc=0
  else
    rc=$?
  fi
  echo "[entrypoint] ffmpeg exited rc=$rc"

  if [ "$rc" -eq 0 ]; then
    exit 0
  fi

  if [ "$attempt" -ge "$INPUT_CONNECT_MAX_RETRIES" ]; then
    echo "[entrypoint] giving up after $attempt attempts"
    exit "$rc"
  fi

  echo "[entrypoint] retrying in ${INPUT_CONNECT_RETRY_SECONDS}s"
  sleep "$INPUT_CONNECT_RETRY_SECONDS"
done
