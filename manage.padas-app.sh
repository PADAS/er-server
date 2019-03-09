#!/bin/bash

###############################################################
# Manage the padas-app infrastructure resources
#
###############################################################


MANAGE_PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT=padas-app
CONCOURSE_URL=https://ci.pamdas.org
ELASTIC_URL=elastic.vulcancloud.io
LOGSTASH_URL=nginx-udp.vulcancloud.io:5045
TOOLS_VERSION=1.0.408
VCLOUD_SERVICE_URL=http://vcloud.vulcancloud.io:5000/
CONCOURSE_TEAM=main
AZURE_SUBSCRIPTION=DAS
IAAS=gcp

### DO NOT EDIT BELOW THIS LINE
### Below this line is generic copy pasted from the master in infrastructure

# If this is set we will serve up 8001 in this container to this port on the host
K8S_PROXY_PORT=$1

IMAGE_NAME=gcr.io/ss-infrastructure-public/platform/tools:$TOOLS_VERSION
CONTAINER_NAME=vp_tools_$PROJECT
VAULT_ADDR=https://vault.vulcancloud.io:8200

function forward_port_if_set()
{
    if [ -n "$K8S_PROXY_PORT" ]; then
        echo "-p$K8S_PROXY_PORT:8001"
    else
        echo "-eCANNOT_PROXY=true"
    fi
}

if [ ! "$(docker ps -aq -f status=exited -f name=$CONTAINER_NAME)" ]; then
    docker run -it \
        -e PROJECT=$PROJECT \
        -e VAULT_ADDR=$VAULT_ADDR \
        -e VAULT_SKIP_VERIFY=true \
        -e CONCOURSE_URL=$CONCOURSE_URL \
        -e ELASTIC_URL=$ELASTIC_URL \
        -e AZURE_LOGIN=true \
        -e AZURE_SUBSCRIPTION=$AZURE_SUBSCRIPTION \
        --name $CONTAINER_NAME \
        -v $CONTAINER_NAME-root:/root \
        --entrypoint run/startup.sh \
        $IMAGE_NAME

    if [ $? != 0 ]; then
        echo "Login failed. Rerun manage script to try again. Deleting container: "
        docker rm $CONTAINER_NAME
        exit 1
    fi
fi

docker run -it --rm \
    --volumes-from $CONTAINER_NAME \
    -e PROJECT=$PROJECT \
    -e CONCOURSE_URL=$CONCOURSE_URL \
    -e LOGSTASH_URL=$LOGSTASH_URL \
    -e ELASTIC_URL=$ELASTIC_URL \
    -e CONCOURSE_TEAM=$CONCOURSE_TEAM \
    -e VCLOUD_SERVICE_URL=$VCLOUD_SERVICE_URL \
    -e VAULT_ADDR=$VAULT_ADDR \
    -e VAULT_SKIP_VERIFY=true \
    -e K8S_PROXY_PORT="$K8S_PROXY_PORT" \
    "$(forward_port_if_set "$K8S_PROXY_PORT")" \
    -e USERNAME="$(whoami)" \
    -e TOOLS_CONTAINER_VERSION=$TOOLS_VERSION \
    -e IAAS=$IAAS \
    -e AZURE_SUBSCRIPTION=$AZURE_SUBSCRIPTION \
    -v "$MANAGE_PROJECT_DIR/ci:/vulcan-platform-tools/ci" \
    -v "$MANAGE_PROJECT_DIR/deployment:/vulcan-platform-tools/deployment" \
    -v "$(pwd):/vulcan-platform-tools/workdir" \
    $IMAGE_NAME
