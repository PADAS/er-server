# gdal image: ghcr.io/osgeo/gdal:ubuntu-small-3.4.3
# Ubuntu 20.04.4 LTS
# python 3.8.10
FROM ghcr.io/osgeo/gdal:ubuntu-small-3.9.3
LABEL org.opencontainers.image.description maintainer="EarthRanger Developers developers@earthranger.com"



RUN apt-get update; apt-get install -y --no-install-recommends \
  git \
  libpq-dev \
  libmagic-dev \
  build-essential \
  libkrb5-dev \
  postgresql-client \
  && apt-get autoremove --yes \
  && rm -rf /var/lib/{apt,dpkg,cache,log}

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /das
ADD ./dependencies /das/dependencies
ADD ./pyproject.toml /das/
ADD ./uv.lock /das/

RUN uv sync --no-dev

ARG built_version=""

EXPOSE 8000
EXPOSE 5400

ENV LC_ALL C.UTF-8
ENV LANG C.UTF-8
ENV LANGUAGE C.UTF-8

ENV BUILT_VERSION=${built_version}

ENV DJANGO_SETTINGS_MODULE=das_server.local_settings_docker

ARG ARCH=x86_64
ENV GDAL_LIBRARY_PATH=/lib/${ARCH}-linux-gnu/libgdal.so
ENV GEOS_LIBRARY_PATH=/lib/${ARCH}-linux-gnu/libgeos_c.so.1

# Default service name
ENV SERVICE_NAME=api_server
ADD ./das /das

# Collect static files (using a stub database)
RUN uv run python manage.py collectstatic --noinput --settings=das_server.local_settings_nodb
ENV VIRTUAL_ENV=/das/.venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

CMD ["/das/start_scripts/start.sh"]
