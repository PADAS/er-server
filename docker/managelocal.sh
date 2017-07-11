#!/bin/bash

set -x

COMMAND=$@
CONTAINER_NAME="das_api"
IMAGE_NAME="gcr.io/padas-app/api"
DOCKER_COMMAND="exec"
OPTS="-it -v $(pwd)/das:/var/www/app"
TODO="manage.py $COMMAND --settings=das_server.local_settings_docker"

if [[ -n "$COMMAND" ]]; then
    CID=$(docker ps -q -f name=$CONTAINER_NAME)
    if [[ -z $CID ]]; then
        docker run $OPTS --entrypoint="python3" $IMAGE_NAME $TODO 
    else
        docker exec -it $CONTAINER_NAME python3 $TODO
    fi

else
    echo "argument error"
fi
