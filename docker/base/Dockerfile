FROM ubuntu:16.04
MAINTAINER Chris Doehring, chrisdo@vulcan.com & Matt Korwel, mattko@vulcan.com  

RUN apt-get update \
    && apt-get install -y \
    nginx \
    git \
    libpq-dev \
    ssh \
    python3-pip \
    && apt-get autoremove \
    && apt-get clean

VOLUME /workspace
WORKDIR /workspace

ADD ./dependencies /workspace/dependencies
RUN dpkg -i /workspace/dependencies/proj_4.9.3-1_amd64.deb
RUN dpkg -i /workspace/dependencies/gdal_2.1.3-1_amd64.deb
RUN dpkg -i /workspace/dependencies/geos_3.6.1-1_amd64.deb
ENV LD_LIBRARY_PATH "/usr/local/lib"

RUN pip3 install -U "pip"
RUN pip3 install -r /workspace/dependencies/requirements.txt -r /workspace/dependencies/requirements-pinned.txt
RUN pip3 install -r /workspace/dependencies/requirements-dev.txt

ADD ./das /var/www/das

VOLUME /tmp
WORKDIR /var/www/das
ADD ./docker/base/wait_for.sh /var/www/das/wait_for.sh

ENV DJANGO_SETTINGS_MODULE=das_server.local_settings_docker
ADD ./docker/base/start.sh /var/www/das/start.sh
ENTRYPOINT ["/var/www/das/start.sh"]