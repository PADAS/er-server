ARG app_tag=latest
FROM gcr.io/padas-app/base:${app_tag}

ARG version=""

ADD ./start_scripts/start*.sh /var/www/app/start_scripts/
ADD ./start_scripts/start.sh /var/www/app/start.sh

EXPOSE 8000
EXPOSE 5400

ENV VERSION=${version}

# TODO: Validate this is necessary.
VOLUME /tmp

ENV DJANGO_SETTINGS_MODULE=das_server.local_settings_docker

ENV SERVICE_NAME=api_server

WORKDIR /var/www/app
