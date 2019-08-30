ARG app_tag=latest
FROM gcr.io/padas-app/app:${app_tag}

HEALTHCHECK --interval=30s --timeout=2s \
  CMD curl -f http://localhost:8000/socket.io/ || exit 1

# TODO: Look into adding this into start script
ENV EVENTLET_SHOULDPATCH=True
ADD ./start.sh /var/www/app/start.sh
EXPOSE 8000
