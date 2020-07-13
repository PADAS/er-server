ARG app_tag=latest
FROM gcr.io/padas-app/app:${app_tag}
ADD ./start.sh /var/www/app/start.sh

ADD ./beat_liveness.py /var/www/app/beat_liveness.py
ADD ./beat_liveness.sh /var/www/app/beat_liveness.sh

WORKDIR /var/www/app
RUN chmod +x beat_liveness.py beat_liveness.sh
