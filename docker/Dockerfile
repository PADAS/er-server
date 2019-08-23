ARG app_tag=latest
FROM gcr.io/padas-app/app:${app_tag}

ARG version=""

ADD ./start_scripts/start*.sh /var/www/app/

EXPOSE 8000
EXPOSE 5400

ENV VERSION=${version}

WORKDIR /var/www/app
CMD start_api_server.sh

