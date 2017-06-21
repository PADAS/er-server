#!/bin/bash

COMMAND=$@
docker-compose stop $COMMAND
docker-compose rm -f $COMMAND 
docker-compose -f docker-compose.yml -f compose-dev.yml up -d $COMMAND
docker-compose logs -f $COMMAND
