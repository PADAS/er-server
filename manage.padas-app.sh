#!/bin/bash -e

###############################################################
# Manage the padas-app infrastructure resources
#
###############################################################

PROJECT=padas-app
CONCOURSE_URL=https://35.197.64.22

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
        -v $(pwd):/workdir \
        --entrypoint /run/startup.sh \
        gcr.io/ss-infrastructure/platform/tools
else
    docker run -it --rm \
        --volumes-from $CONTAINER_NAME \
        -e PROJECT=$PROJECT \
        -e CONCOURSE_URL=$CONCOURSE_URL \
        -e VAULT_ADDR=$VAULT_ADDR \
        -e VAULT_SKIP_VERIFY=true \
        -v $(pwd):/workdir \
        gcr.io/ss-infrastructure/platform/tools
fi