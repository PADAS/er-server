ARG base_tag=latest
FROM gcr.io/padas-app/app:${base_tag}

RUN apt-get install curl

HEALTHCHECK --interval=30s --timeout=2s \
  CMD curl -f http://localhost:8000/socket.io/ || exit 1

ENV EVENTLET_SHOULDPATCH=True
ADD ./start.sh /var/www/app/start.sh
EXPOSE 8000
