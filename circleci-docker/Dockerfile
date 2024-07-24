FROM ghcr.io/osgeo/gdal:ubuntu-small-3.4.1
LABEL org.opencontainers.image.description maintainer="EarthRanger Developers developers@earthranger.com"

RUN apt-get update; apt-get install -y pip git libmagic-dev postgresql-client libpq-dev; \
  apt-get clean autoclean; \
  apt-get autoremove --yes;\
  rm -rf /var/lib/{apt,dpkg,cache,log}

WORKDIR /das
COPY ./dependencies /das/dependencies

RUN python3 -m pip install pip --upgrade
RUN pip install --disable-pip-version-check --no-cache-dir -r /das/dependencies/requirements.txt -r \
  /das/dependencies/requirements-pinned.txt --find-links /das/dependencies/wheelhouse;

ARG built_version=""

EXPOSE 8000
EXPOSE 5400

ENV LC_ALL C.UTF-8
ENV LANG C.UTF-8
ENV LANGUAGE C.UTF-8

ENV BUILT_VERSION=${built_version}

ENV DJANGO_SETTINGS_MODULE=das_server.local_settings_docker

# Default service name
ENV SERVICE_NAME=api_server
ADD ./das /das

# Collect static files (using a stub database)
RUN python3 manage.py collectstatic --noinput --settings=das_server.local_settings_nodb

CMD ["/das/start_scripts/start.sh"]
