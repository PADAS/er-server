#!/bin/bash -e

###############################################################
# Manage the padas-app infrastructure resources
###############################################################

MANAGE_PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT=padas-app
CONCOURSE_URL=https://35.197.64.22

IMAGE_NAME=gcr.io/ss-infrastructure-public/platform/tools:0.0.15
CONTAINER_NAME=vp_tools_$PROJECT
VAULT_ADDR=https://35.197.70.36:8200

if [ ! "$(docker ps -aq -f status=exited -f name=$CONTAINER_NAME)" ]; then
    docker run -it \
        -e PROJECT=$PROJECT \
        -e VAULT_ADDR=$VAULT_ADDR \
        -e VAULT_SKIP_VERIFY=true \
        -e CONCOURSE_URL=$CONCOURSE_URL \
        --name $CONTAINER_NAME \
        -v $CONTAINER_NAME-root:/root \
        --entrypoint run/startup.sh \
        $IMAGE_NAME
fi

docker run -it --rm \
    --volumes-from $CONTAINER_NAME \
    -e PROJECT=$PROJECT \
    -e CONCOURSE_URL=$CONCOURSE_URL \
    -e VAULT_ADDR=$VAULT_ADDR \
    -e VAULT_SKIP_VERIFY=true \
    -e USERNAME=$(whoami) \
    -v $MANAGE_PROJECT_DIR/ci:/vulcan-platform-tools/ci \
    -v $MANAGE_PROJECT_DIR/deployment:/vulcan-platform-tools/deployment \
    -v $(pwd):/vulcan-platform-tools/workdir \
    $IMAGE_NAME
