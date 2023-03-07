FROM ubuntu:bionic
ARG PYTHON_VERSION_ID="3.7"
ARG CP_VER="cp37"

ARG PYTHON_PACKAGES="python${PYTHON_VERSION_ID} python${PYTHON_VERSION_ID}-dev python${PYTHON_VERSION_ID}-distutils"
RUN apt-get update && apt-get install --no-install-recommends -yq software-properties-common \
     && add-apt-repository ppa:deadsnakes/ppa && apt-get update \
     && apt-get install -yq --no-install-recommends ${PYTHON_PACKAGES}
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
    && apt-get autoremove

RUN echo ogrinfo --version

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
RUN ldconfig
RUN echo gdal-config --version

RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python${PYTHON_VERSION_ID} 4
RUN if [ "$CP_VER" = "cp36" ]; then wget https://bootstrap.pypa.io/pip/3.6/get-pip.py ; else wget https://bootstrap.pypa.io/get-pip.py; fi     ; python3 get-pip.py; pip3 install numpy==1.19.5 pyopenssl
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
