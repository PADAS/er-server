#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
docker login -e 1234@5678.com -u _json_key -p "$(cat $DIR/../../../das-push.json)" https://gcr.io

docker push gcr.io/das-app/base:latest
docker push gcr.io/das-app/app:latest
docker push gcr.io/das-app/postgis:latest
docker push gcr.io/das-app/api:latest
docker push gcr.io/das-app/rt_api:latest
docker push gcr.io/das-app/beat:latest
docker push gcr.io/das-app/worker:latest
docker push gcr.io/das-app/mql:latest
docker push gcr.io/das-app/nginx:latest
docker push gcr.io/das-app/web:latest
docker push gcr.io/das-app/web-react:latest
