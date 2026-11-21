#!/bin/sh

nohup sh -c '
  while inotifywait -e create,delete,modify,move,close_write /etc/nginx/nginx-rules; do
    echo "[nginx-rules] change, reload"
    nginx -s reload || true
  done
' >/proc/1/fd/1 2>/proc/1/fd/2 &
