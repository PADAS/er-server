ARG app_tag=latest
FROM gcr.io/padas-app/app:${app_tag}

ARG version=""

ADD docker/API/start.sh /var/www/app/start.sh

EXPOSE 8000
EXPOSE 5400

ENV VERSION=${version}

