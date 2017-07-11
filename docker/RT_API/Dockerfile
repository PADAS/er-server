ARG base_tag=latest
FROM gcr.io/padas-app/app:${base_tag}
ENV EVENTLET_SHOULDPATCH=True
ADD ./start.sh /var/www/app/start.sh
EXPOSE 8000