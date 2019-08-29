ARG app_tag=latest
FROM gcr.io/padas-app/app:${app_tag}

ARG version=""

ADD ./start_scripts/start*.sh /var/www/app/start_scripts/
ADD ./start_scripts/start.sh /var/www/app/start.sh

EXPOSE 8000
EXPOSE 5400

ENV VERSION=${version}

ENV SERVICE_NAME=api_server

WORKDIR /var/www/app
