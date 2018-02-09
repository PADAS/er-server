#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
docker login -e 1234@5678.com -u _json_key -p "$(cat $DIR/../../../das-push.json)" https://gcr.io

docker tag gcr.io/das-app/base gcr.io/das-app/base:release
docker tag gcr.io/das-app/app gcr.io/das-app/app:release
docker tag gcr.io/das-app/postgis gcr.io/das-app/postgis:release
docker tag gcr.io/das-app/api gcr.io/das-app/api:release
docker tag gcr.io/das-app/rt_api gcr.io/das-app/rt_api:release
docker tag gcr.io/das-app/beat gcr.io/das-app/beat:release
docker tag gcr.io/das-app/worker gcr.io/das-app/worker:release
docker tag gcr.io/das-app/mql gcr.io/das-app/mql:release
docker tag gcr.io/das-app/nginx gcr.io/das-app/nginx:release
docker tag gcr.io/das-app/web/app gcr.io/das-app/web/app:release


docker push gcr.io/das-app/base:release
docker push gcr.io/das-app/app:release
docker push gcr.io/das-app/postgis:release
docker push gcr.io/das-app/api:release
docker push gcr.io/das-app/rt_api:release
docker push gcr.io/das-app/beat:release
docker push gcr.io/das-app/worker:release
docker push gcr.io/das-app/mql:release
docker push gcr.io/das-app/nginx:release
docker push gcr.io/das-app/web/app:release

