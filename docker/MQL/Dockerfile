ARG app_tag=latest
FROM gcr.io/padas-app/app:${app_tag}
ADD ./start.sh /var/www/app/start.sh

ADD ./mql_liveness.py /var/www/app/mql_liveness.py
ADD ./mql_liveness.sh /var/www/app/mql_liveness.sh

WORKDIR /var/www/app
RUN chmod +x mql_liveness.py mql_liveness.sh
