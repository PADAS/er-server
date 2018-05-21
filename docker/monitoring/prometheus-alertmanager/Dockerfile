FROM prom/alertmanager:v0.9.1

COPY ./config /config
COPY ./startup /startup

ENTRYPOINT /startup/startup.sh
