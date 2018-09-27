ARG base_tag=latest
ARG hope
FROM gcr.io/padas-app/app:${base_tag}
RUN echo ${hope}
ADD ./start.sh /var/www/app/start.sh

EXPOSE 8000
EXPOSE 5400
