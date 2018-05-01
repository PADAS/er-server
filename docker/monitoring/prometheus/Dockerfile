FROM prom/prometheus:v1.8.2

COPY ./config/prometheus.yml /etc/prometheus
COPY ./rules /rules
COPY ./startup /startup

# This seems to be where more config files are located.
# If we figure out what they're for and want to change them add the below line
# back in and add the corresponding folders from the docker image at 
# /usr/share/prometheus/ into the config directory
# COPY ./config /usr/share/prometheus/

ENTRYPOINT /startup/startup.sh
