#!/bin/bash

COMMAND=$@
docker-compose -f docker-compose.yml -f compose-build.yml build $COMMAND