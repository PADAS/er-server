#!/bin/bash

set -x

COMMAND=$@
CONTAINER_NAME="das_api"
IMAGE_NAME="das/server"
DOCKER_COMMAND="exec"


if [[ -n "$COMMAND" ]]; then
    CID=$(docker ps -q -f name=$CONTAINER_NAME)
    if [[ -z $CID ]]; then
        docker run -it --entrypoint="python3 /var/www/app/manage.py $COMMAND --settings=das_server.local_settings_docker" $IMAGE_NAME 
    else
        docker exec -it $CONTAINER_NAME python3 /var/www/app/manage.py $COMMAND --settings=das_server.local_settings_docker
    fi

else
    echo "argument error"
fi
