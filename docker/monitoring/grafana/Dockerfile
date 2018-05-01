FROM grafana/grafana:4.6.1

RUN apt update && apt install -y at

COPY startup /startup
ENV GF_PATHS_CONFIG /config/grafana-config.ini

COPY config /config

ENTRYPOINT /startup/startup.sh