# See https://github.com/OSGeo/gdal/tree/master/docker
# and here to find the image: https://github.com/OSGeo/gdal/pkgs/container/gdal
# Ubuntu 24.04 LTS
# python 3.10.18

FROM ghcr.io/osgeo/gdal:ubuntu-small-3.12.3
ARG PYTHON_VERSION_ID="3.10"
ARG PYTHON_VERSION="3.10.18"
ARG WORKSPACE_FOLDERNAME="das"
ARG UV_PROJECT_ENVIRONMENT="/home/vscode/.venv"
ENV WORKSPACE_FOLDERNAME=${WORKSPACE_FOLDERNAME}

# [Option] Install zsh
ARG INSTALL_ZSH="true"
# [Option] Upgrade OS packages to their latest versions
ARG UPGRADE_PACKAGES="true"
# Install needed packages and setup non-root user. Use a separate RUN statement to add your own dependencies.
ARG USERNAME=vscode
ARG USER_UID=2000
ARG USER_GID=$USER_UID
RUN apt-get update && apt-get install build-essential software-properties-common sudo -y && add-apt-repository -y ppa:git-core/ppa && apt-get update && apt-get install git -y

# Keeps Python from generating .pyc files in the container
ENV PYTHONDONTWRITEBYTECODE=True \
    PYTHONUNBUFFERED=True \
    UV_LINK_MODE=copy

RUN groupadd --gid $USER_GID $USERNAME \
    && useradd --uid $USER_UID --gid $USER_GID -m $USERNAME \
    && echo $USERNAME ALL=\(root\) NOPASSWD:ALL > /etc/sudoers.d/$USERNAME \
    && chmod 0440 /etc/sudoers.d/$USERNAME

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
    vim \
    && apt-get autoremove

# Tag must satisfy required-version in pyproject.toml ([tool.uv])
COPY --from=ghcr.io/astral-sh/uv:0.12.1 /uv /uvx /bin/

# Install Google Cloud SDK
RUN echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" | tee -a /etc/apt/sources.list.d/google-cloud-sdk.list && curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg && apt-get update -y && apt-get install google-cloud-cli -y

WORKDIR /workspaces/${WORKSPACE_FOLDERNAME}
ADD ./dependencies /workspaces/${WORKSPACE_FOLDERNAME}/dependencies
ADD ./pyproject.toml /workspaces/${WORKSPACE_FOLDERNAME}/
ADD ./uv.lock /workspaces/${WORKSPACE_FOLDERNAME}/

USER vscode

RUN uv sync --group dev --no-install-project
ENV VIRTUAL_ENV=${UV_PROJECT_ENVIRONMENT}
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

SHELL ["/bin/bash", "-c"]
