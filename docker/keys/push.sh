#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
docker login -e 1234@5678.com -u _json_key -p "$(cat $DIR/push.json)" https://gcr.io

docker push gcr.io/padas-app/base
docker push gcr.io/padas-app/postgis
docker push gcr.io/padas-app/api
docker push gcr.io/padas-app/rt_api
docker push gcr.io/padas-app/beat
docker push gcr.io/padas-app/worker
docker push gcr.io/padas-app/mql
docker push gcr.io/padas-app/nginx
docker push gcr.io/padas-app/web