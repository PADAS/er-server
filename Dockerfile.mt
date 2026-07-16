FROM europe-west3-docker.pkg.dev/serca-artifact-registry/virtual-docker/osgeo/gdal:ubuntu-small-3.12.3
LABEL org.opencontainers.image.description="" maintainer="EarthRanger Developers developers@earthranger.com"

RUN apt-get update && apt-get install -y --no-install-recommends \
  git \
  libpq-dev \
  libmagic-dev \
  build-essential \
  libkrb5-dev \
  postgresql-client \
  && apt-get autoremove --yes \
  && rm -rf /var/lib/{apt,dpkg,cache,log}

# Tag must satisfy required-version in pyproject.toml ([tool.uv])
COPY --from=europe-west3-docker.pkg.dev/serca-artifact-registry/virtual-docker/astral-sh/uv:0.11.28 /uv /uvx /bin/

WORKDIR /das
ADD ./dependencies /das/dependencies
ADD ./pyproject.toml /das/
ADD ./uv.lock /das/

# Install only third-party dependencies (cached layer).
# --no-install-project skips building the local 'das' package,
# avoiding the dynamic version resolution that needs source code.
RUN uv venv --python=python3.10
RUN uv sync --no-dev --no-install-project

ARG built_version=""

EXPOSE 8000
EXPOSE 5400

ENV LC_ALL=C.UTF-8
ENV LANG=C.UTF-8
ENV LANGUAGE=C.UTF-8

ENV BUILT_VERSION="${built_version}"

ENV DJANGO_SETTINGS_MODULE=das_server.local_settings_docker

ARG ARCH=x86_64
ENV GDAL_LIBRARY_PATH=/lib/${ARCH}-linux-gnu/libgdal.so
ENV GEOS_LIBRARY_PATH=/lib/${ARCH}-linux-gnu/libgeos_c.so.1

ADD ./das /das

# Default service name
ENV SERVICE_NAME=api_server
ENV VIRTUAL_ENV=/das/.venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Collect static files (using a stub database)
RUN python manage.py collectstatic --noinput --settings=das_server.local_settings_nodb

CMD ["/das/start_scripts/start.sh"]
