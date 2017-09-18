ARG base_tag=latest
FROM gcr.io/padas-app/app:${base_tag}
RUN apt-get install curl
ADD ./start.sh /var/www/app/start.sh
EXPOSE 8000
