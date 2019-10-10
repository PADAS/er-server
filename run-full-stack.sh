#!/bin/bash

docker-compose -f docker-compose.yml -f compose-dev.yml -f compose-build.yml -f compose-build-web.yml -f compose-notebook.yml $*
