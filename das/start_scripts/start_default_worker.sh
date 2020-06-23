#!/bin/sh
. $(dirname "$0")/wait_for.sh
wait_for $API_HOST $API_PORT

celery -A das_server worker -Q default,maintenance -l info -c 10 -P gevent --without-gossip -n default
