ARG base_tag=latest
FROM gcr.io/padas-app/app:${base_tag}

ARG version=""

ADD ./start.sh /var/www/app/start.sh

EXPOSE 8000
EXPOSE 5400

ENV VERSION=${version}

