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

ENV DJANGO_SETTINGS_MODULE=das_server.local_settings_docker
CMD ["/var/www/das/startapp.sh"]
EXPOSE 8000