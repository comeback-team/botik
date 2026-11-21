FROM nginx:1.31-alpine

RUN apk add --no-cache inotify-tools

COPY watch-rules.sh /docker-entrypoint.d/99-watch-rules.sh
RUN chmod +x /docker-entrypoint.d/99-watch-rules.sh
