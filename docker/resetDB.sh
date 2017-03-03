#!/bin/bash

docker-compose stop postgis 
docker-compose rm -f postgis 
docker-compose up -d api