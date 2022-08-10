FROM ubuntu:18.04
LABEL maintainer="EarthRanger Developers developers@earthranger.com"

ARG PYTHON_VERSION_ID="3.7"
ARG CP_VER="cp37"

RUN apt-get update

RUN apt-get install -y \
    git \
    libpq-dev \
    python3-pip \
    python-numpy \
    python-numpy-dev \
    libgdal-dev \
    python-gdal\
    curl \
    python3-openssl \
    libssl-dev \
    wget \
    gnupg \
    locales locales-all \
    && apt-get autoremove

WORKDIR /workspace

ADD ./dependencies /workspace/dependencies

SHELL ["/bin/bash", "-c"]

RUN arch=$(uname -i); \
 if [[ $arch == x86_64* ]]; then \
   export arch_name="amd64"; \
 elif  ([[ $arch == arm* ]] || [[ $arch == aarch* ]]); then \
    export arch_name="arm64"; \
 fi ; \
 curl https://storage.googleapis.com/er-dependencies/geos_3.9.1-1_${CP_VER}_${arch_name}.deb -o geos.deb -s && dpkg -i --force-all geos.deb ; \
 curl https://storage.googleapis.com/er-dependencies/proj_7.2.1-1_${CP_VER}_${arch_name}.deb -o proj.deb -s && dpkg -i --force-all proj.deb ; \
 curl https://storage.googleapis.com/er-dependencies/gdal_3.4.1-1_${CP_VER}_${arch_name}.deb -o gdal.deb -s && dpkg -i --force-all gdal.deb


ENV LD_LIBRARY_PATH "/usr/local/lib"

RUN wget --quiet -O - https://www.postgresql.org/media/keys/ACCC4CF8.asc | apt-key add -
RUN /bin/sh -c 'echo "deb http://apt.postgresql.org/pub/repos/apt/ bionic-pgdg main" >> /etc/apt/sources.list.d/postgresql.list'
RUN apt-get update

RUN apt-get -y purge python3.6
RUN apt-get -y install python3-pip python3.7-dev
RUN apt-get -y install python3.7
RUN python3 -m pip install pip

RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.7 2
RUN /bin/sh -c 'python3 -V'

RUN DEBIAN_FRONTEND=noninteractive apt-get install -y postgresql-9.6-postgis-2.4
RUN apt-get install -y postgresql-9.6-postgis-2.4-scripts
RUN apt-get clean

RUN pip3 install -U "pip"
RUN pip3 install numpy==1.19.5

RUN rm -rf /usr/lib/python3/dist-packages/GDAL-2.2.2.*
RUN pip3 install -r /workspace/dependencies/requirements.txt -r /workspace/dependencies/requirements-pinned.txt --no-cache-dir -f /workspace/dependencies/wheelhouse
#RUN pip3 install django-debug-toolbar

ARG built_version=""

ADD ./das /var/www/app

EXPOSE 8000
EXPOSE 5400

ENV LC_ALL C.UTF-8
ENV LANG C.UTF-8
ENV LANGUAGE C.UTF-8

ENV BUILT_VERSION=${built_version}

# TODO: Validate this is necessary.
VOLUME /tmp

ENV DJANGO_SETTINGS_MODULE=das_server.local_settings_docker

# Default service name
ENV SERVICE_NAME=api_server

WORKDIR /var/www/app

# Collect static files (using a stub database)
RUN python3 manage.py collectstatic --noinput --settings=das_server.local_settings_nodb

CMD ["/var/www/app/start_scripts/start.sh"]
