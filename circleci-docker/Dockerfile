FROM ubuntu:18.04
# MAINTAINER Chris Doehring, chrisdo@vulcan.com & Matt Korwel, mattko@vulcan.com, lorainek@vulcan.com
#
# RUN apt-get update
#
# RUN apt-get install -y \
#    git \
#    libpq-dev \
#    python3-pip \
#    python-numpy \
#    python-numpy-dev \
#    libgdal-dev \
#    curl \
#    python3-openssl \
#    libssl-dev \
#    wget \
#    gnupg \
#    && apt-get autoremove \
#    && apt-get clean
#
# WORKDIR /workspace
#
# ADD ./dependencies /workspace/dependencies
# RUN dpkg -i --force-all /workspace/dependencies/gdal_2.2.3-1_cp36_amd64.deb
# RUN dpkg -i --force-all /workspace/dependencies/geos_3.6.2-1_cp36_amd64.deb
# RUN dpkg -i --force-all /workspace/dependencies/proj_4.9.3-1_cp36_amd64.deb
# ENV LD_LIBRARY_PATH "/usr/local/lib"
#
# RUN wget --quiet -O - https://www.postgresql.org/media/keys/ACCC4CF8.asc | apt-key add -
# RUN /bin/sh -c 'echo "deb http://apt.postgresql.org/pub/repos/apt/ bionic-pgdg main" >> /etc/apt/sources.list.d/postgresql.list'
# RUN apt-get update
# RUN DEBIAN_FRONTEND=noninteractive apt-get install -y postgresql-9.6-postgis-2.4
# RUN apt-get install -y postgresql-9.6-postgis-2.4-scripts
#
# RUN pip3 install -U "pip"
# RUN pip3 install numpy
#
# RUN rm -rf /usr/lib/python3/dist-packages/GDAL-2.2.2.*
# RUN pip3 install -r /workspace/dependencies/requirements.txt -r /workspace/dependencies/requirements-pinned.txt --no-cache-dir -f /workspace/dependencies/wheelhouse
# #RUN pip3 install django-debug-toolbar
#
# ARG version=""
#
# ADD ./das /var/www/app
#
# EXPOSE 8000
# EXPOSE 5400
#
# ENV VERSION=${version}
#
# # TODO: Validate this is necessary.
# VOLUME /tmp
#
# ENV DJANGO_SETTINGS_MODULE=das_server.local_settings_docker
#
# # Default service name
# ENV SERVICE_NAME=api_server
#
# WORKDIR /var/www/app

CMD ["/var/www/app/start_scripts/start.sh"]
