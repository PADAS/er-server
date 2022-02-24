FROM ubuntu:bionic
ARG PYTHON_PACKAGES="python3.6 python3-pip python3-venv"
RUN apt-get update && apt-get install --no-install-recommends -yq software-properties-common \
     && add-apt-repository ppa:deadsnakes/ppa && apt-get update \
     && apt-get install -yq --no-install-recommends ${PYTHON_PACKAGES} \
     && pip3 install --no-cache-dir --upgrade pip setuptools wheel
ARG PYTHON_VERSION="os-provided"

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
RUN apt-get update && export DEBIAN_FRONTEND=noninteractive \
    # Remove imagemagick due to https://security-tracker.debian.org/tracker/CVE-2019-10131
    && apt-get purge -y imagemagick imagemagick-6-common \
    # Install common packages, non-root user
    && bash /tmp/library-scripts/common-debian.sh "${INSTALL_ZSH}" "${USERNAME}" "${USER_UID}" "${USER_GID}" "${UPGRADE_PACKAGES}" "true" "true" \
    && apt-get autoremove -y && apt-get clean -y && rm -rf /var/lib/apt/lists/*

# Setup default python tools in a venv via pipx to avoid conflicts
ENV PIPX_HOME=/usr/local/py-utils \
    PIPX_BIN_DIR=/usr/local/py-utils/bin
ENV PATH=${PATH}:${PIPX_BIN_DIR}
RUN bash /tmp/library-scripts/python-debian.sh "os-provided" "/usr/local" "${PIPX_HOME}" "${USERNAME}" \ 
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
    netbase \
    python3-numpy \
    python3-numpy-dev \
    #libgdal-dev \
    curl \
    python3-openssl \
    postgresql-client \
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


# [Optional] If your pip requirements rarely change, uncomment this section to add them to the image.
# COPY requirements.txt /tmp/pip-tmp/
# RUN pip3 --disable-pip-version-check --no-cache-dir install -r /tmp/pip-tmp/requirements.txt \
#    && rm -rf /tmp/pip-tmp

# [Optional] Uncomment this section to install additional OS packages.
# RUN apt-get update && export DEBIAN_FRONTEND=noninteractive \
#     && apt-get -y install --no-install-recommends <your-package-list-here>

# [Optional] Uncomment this line to install global node packages.
# RUN su vscode -c "source /usr/local/share/nvm/nvm.sh && npm install -g <your-package-here>" 2>&1
