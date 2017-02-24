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
RUN dpkg -i /workspace/dependencies/proj_4.9.2-1_amd64.deb
RUN dpkg -i /workspace/dependencies/gdal_1.11.4-1_amd64.deb
RUN dpkg -i /workspace/dependencies/geos_3.5.0-1_amd64.deb
ENV LD_LIBRARY_PATH "/usr/local/lib"

RUN pip3 install -U "pip"
ADD ./requirements.txt /workspace/requirements.txt
ADD ./requirements-dev.txt /workspace/requirements-dev.txt
RUN pip3 install -r /workspace/requirements.txt
RUN pip3 install -r /workspace/requirements-dev.txt

ADD ./das /var/www/das
ADD ./startapp.sh /workspace/startapp.sh
ENTRYPOINT ["/workspace/startapp.sh"]
EXPOSE 8000