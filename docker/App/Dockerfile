ARG base_tag=latest
FROM gcr.io/padas-app/base:${base_tag}

ADD ./das /var/www/app

VOLUME /tmp
WORKDIR /var/www/app

ENV DJANGO_SETTINGS_MODULE=das_server.local_settings_docker
