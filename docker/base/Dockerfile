FROM ubuntu:17.10
MAINTAINER Chris Doehring, chrisdo@vulcan.com & Matt Korwel, mattko@vulcan.com  

RUN apt-get update \
    && apt-get install -y \
    git \
    libpq-dev \
    python3-pip \
    python-numpy \
    python-numpy-dev \
    libgdal-dev \
    curl \
    && apt-get autoremove \
    && apt-get clean

VOLUME /workspace
WORKDIR /workspace

ADD ./dependencies /workspace/dependencies
RUN dpkg -i --force-all /workspace/dependencies/gdal_2.2.3-1_cp36_amd64.deb
RUN dpkg -i --force-all /workspace/dependencies/geos_3.6.2-1_cp36_amd64.deb
RUN dpkg -i --force-all /workspace/dependencies/proj_4.9.3-1_cp36_amd64.deb
ENV LD_LIBRARY_PATH "/usr/local/lib"

RUN pip3 install -U "pip"
RUN pip3 install numpy

RUN rm -rf /usr/lib/python3/dist-packages/GDAL-2.2.2.*
RUN pip3 install -r /workspace/dependencies/requirements.txt -r /workspace/dependencies/requirements-pinned.txt --no-cache-dir -f /workspace/dependencies/wheelhouse
#RUN pip3 install django-debug-toolbar

RUN mkdir -p /var/www/app && mkdir -p /startup
ADD ./docker/base/start.sh /var/www/app/start.sh
ADD ./docker/base/wait_for.sh /startup/wait_for.sh

ENTRYPOINT ["/var/www/app/start.sh"]
