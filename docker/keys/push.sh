#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
docker login -e 1234@5678.com -u _json_key -p "$(cat $DIR/../../../das-push.json)" https://gcr.io

docker push gcr.io/padas-app/base:latest
docker push gcr.io/padas-app/postgis:latest
docker push gcr.io/padas-app/api:latest
docker push gcr.io/padas-app/rt_api:latest
docker push gcr.io/padas-app/beat:latest
docker push gcr.io/padas-app/worker:latest
docker push gcr.io/padas-app/mql:latest
docker push gcr.io/padas-app/nginx:latest
docker push gcr.io/padas-app/web:latest