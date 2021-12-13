# See here for image contents: https://github.com/microsoft/vscode-dev-containers/blob/v0.202.3/containers/python-3/.devcontainer/base.Dockerfile
# [Choice] Python version (use -bullseye variants on local arm64/Apple Silicon): 3, 3.9, 3.8, 3.7, 3.6, 3-bullseye, 3.9-bullseye, 3.8-bullseye, 3.7-bullseye, 3.6-bullseye, 3-buster, 3.9-buster, 3.8-buster, 3.7-buster, 3.6-buster
#ARG VARIANT=3-bullseye
#FROM mcr.microsoft.com/vscode/devcontainers/python:0-${VARIANT}
ARG VARIANT=18.04
FROM mcr.microsoft.com/vscode/devcontainers/base:${VARIANT}

RUN apt-get update \
  && apt-get install -y python3-pip python3-dev \
  && cd /usr/local/bin \
  && ln -s /usr/bin/python3 python \
  && pip3 install --upgrade pip

# [Optional] Allow the vscode user to pip install globally w/o sudo
ENV PIP_TARGET=/usr/local/pip-global
ENV PYTHONPATH=${PIP_TARGET}:${PYTHONPATH}
ENV PATH=${PIP_TARGET}/bin:${PATH}
RUN if ! cat /etc/group | grep -e "^pip-global:" > /dev/null 2>&1; then groupadd -r pip-global; fi \
    && usermod -a -G pip-global vscode \
    && umask 0002 && mkdir -p ${PIP_TARGET} \
    && chown :pip-global ${PIP_TARGET} \
    && ( [ ! -f "/etc/profile.d/00-restore-env.sh" ] || sed -i -e "s/export PATH=/export PATH=\/usr\/local\/pip-global:/" /etc/profile.d/00-restore-env.sh )

# [Choice] Node.js version: none, lts/*, 16, 14, 12, 10
# ARG NODE_VERSION="none"
# RUN if [ "${NODE_VERSION}" != "none" ]; then su vscode -c "umask 0002 && . /usr/local/share/nvm/nvm.sh && nvm install ${NODE_VERSION} 2>&1"; fi

# Keeps Python from generating .pyc files in the container
ENV PYTHONDONTWRITEBYTECODE=1
# Turns off buffering for easier container logging
ENV PYTHONUNBUFFERED=1

RUN apt-get update && export DEBIAN_FRONTEND=noninteractive \
    && apt-get -y install --no-install-recommends \
    git \
    libpq-dev \
    libjpeg-dev \
    libtiff-dev \
    python3-numpy \
    python3-numpy-dev \
    #libgdal-dev \
    curl \
    python3-openssl \
    libssl-dev \
    wget \
    gnupg \
    locales locales-all \
    && apt-get autoremove

WORKDIR /workspace
ADD ./dependencies /workspace/dependencies

RUN dpkg -i --force-all /workspace/dependencies/gdal_3.2.3-1_cp36_amd64.deb
RUN dpkg -i --force-all /workspace/dependencies/geos_3.9.1-1_cp36_amd64.deb
RUN dpkg -i --force-all /workspace/dependencies/proj_7.2.1-1_cp36_amd64.deb
ENV LD_LIBRARY_PATH "/usr/local/lib"
RUN ldconfig

RUN pip3 install numpy==1.19.5

RUN pip3 --disable-pip-version-check --no-cache-dir install -r /workspace/dependencies/requirements-dev.txt -r /workspace/dependencies/requirements-pinned.txt -f /workspace/dependencies/wheelhouse


# [Optional] Uncomment this line to install global node packages.
# RUN su vscode -c "source /usr/local/share/nvm/nvm.sh && npm install -g <your-package-here>" 2>&1