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

RUN pip3 install -U "pip"

VOLUME /workspace
WORKDIR /workspace

ADD ./das /var/www/das/das
ADD ./dependencies /workspace/dependencies

RUN dpkg -i /workspace/dependencies/proj_4.9.2-1_amd64.deb
RUN dpkg -i /workspace/dependencies/gdal_1.11.4-1_amd64.deb
RUN dpkg -i /workspace/dependencies/geos_3.5.0-1_amd64.deb

ENV LD_LIBRARY_PATH "/usr/local/lib:$LD_LIBRARY_PATH"

COPY . /var/www/das/das
# ADD startapp.sh /root/startapp.sh

RUN pip3 install -r /var/www/das/das/requirements.txt
RUN pip3 install -r /var/www/das/das/requirements-dev.txt

CMD []
#ENTRYPOINT ["/usr/bin/python3",]
# ENTRYPOINT ["/root/startapp.sh",]