#!/bin/bash

docker-compose stop
docker-compose rm -vf

docker rmi -f $(docker images -q -f dangling=true)
docker images | grep das > /dev/null
if [ $? -eq 0 ]; then
    docker images | grep das | awk '{print $3}' | xargs docker rmi -f
fi

docker volume prune -f
docker network prune -f

