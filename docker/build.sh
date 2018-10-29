#!/bin/bash

COMMAND=$@
docker-compose -f docker-compose.yml -f compose-build.yml -f compose-dev.yml -f compose-build-web.yml build $COMMAND
