#!/bin/sh
. $(dirname "$0")/wait_for.sh
wait_for $API_HOST $API_PORT

. $(dirname "$0")/django_common_startup.sh

WORKERS=10

celery -A das_server worker -Q default,maintenance -l info -c $WORKERS -P gevent --without-gossip -n default
