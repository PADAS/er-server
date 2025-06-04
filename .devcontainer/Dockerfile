# gdal image: ghcr.io/osgeo/gdal:ubuntu-small-3.4.3
# Ubuntu 20.04.4 LTS
# python 3.8.10
FROM ghcr.io/osgeo/gdal:ubuntu-small-3.4.3
ARG PYTHON_VERSION_ID="3.8"
ARG PYTHON_VERSION="3.8.10"
ARG CP_VER="cp38"


# Copy library scripts to execute
COPY .devcontainer/library-scripts/*.sh .devcontainer/library-scripts/*.env /tmp/library-scripts/

# [Option] Install zsh
ARG INSTALL_ZSH="true"
# [Option] Upgrade OS packages to their latest versions
ARG UPGRADE_PACKAGES="true"
# Install needed packages and setup non-root user. Use a separate RUN statement to add your own dependencies.
ARG USERNAME=vscode
ARG USER_UID=1000
ARG USER_GID=$USER_UID
RUN apt-get update && apt-get install software-properties-common -y && add-apt-repository -y ppa:git-core/ppa && apt-get update && apt-get install git -y
RUN apt-get update && export DEBIAN_FRONTEND=noninteractive \
    # Remove imagemagick due to https://security-tracker.debian.org/tracker/CVE-2019-10131
    && apt-get purge -y imagemagick imagemagick-6-common \
    # Install common packages, non-root user
    && bash /tmp/library-scripts/common-debian.sh "${INSTALL_ZSH}" "${USERNAME}" "${USER_UID}" "${USER_GID}" "${UPGRADE_PACKAGES}" "true" "true" \
    && apt-get autoremove -y && apt-get clean -y && rm -rf /var/lib/apt/lists/*

# Setup default python tools in a venv via pipx to avoid conflicts
ARG PYTHON_PATH=/usr
ENV PIPX_HOME=/usr/local/py-utils \
    PIPX_BIN_DIR=/usr/local/py-utils/bin
ENV PATH=${PATH}:${PIPX_BIN_DIR}
#ENV PATH=${PYTHON_PATH}/bin:${PATH}:${PIPX_BIN_DIR}
RUN bash /tmp/library-scripts/python-debian.sh "os-provided" "${PYTHON_PATH}" "${PIPX_HOME}" "${USERNAME}" \
    && apt-get clean -y && rm -rf /var/lib/apt/lists/*

# [Choice] Node.js version: none, lts/*, 16, 14, 12, 10
ARG NODE_VERSION="none"
ENV NVM_DIR=/usr/local/share/nvm
ENV NVM_SYMLINK_CURRENT=true \
    PATH=${NVM_DIR}/current/bin:${PATH}
RUN bash /tmp/library-scripts/node-debian.sh "${NVM_DIR}" "${NODE_VERSION}" "${USERNAME}" \
    && apt-get clean -y && rm -rf /var/lib/apt/lists/*

# Remove library scripts for final image
RUN rm -rf /tmp/library-scripts

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
    libmagic1 \
    libopenblas-dev \
    liblapack-dev \
    gfortran \
    netbase \
    curl \
    postgresql-client \
    libssl-dev \
    wget \
    gnupg \
    locales locales-all \
    libkrb5-dev \
    && apt-get autoremove

RUN echo ogrinfo --version

# Install Google Cloud SDK
RUN echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" | tee -a /etc/apt/sources.list.d/google-cloud-sdk.list && curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | sudo gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg && apt-get update -y && apt-get install google-cloud-sdk -y


WORKDIR /workspaces/das
ADD ./dependencies /workspaces/das/dependencies

SHELL ["/bin/bash", "-c"]

RUN python3 -m pip install --upgrade pip
RUN pip3 install setuptools==58.0.4

RUN pip3 --disable-pip-version-check --no-cache-dir install -r \
  /workspaces/das/dependencies/requirements-dev.txt -r \
  /workspaces/das/dependencies/requirements-pinned.txt -f /workspaces/das/dependencies/wheelhouse
