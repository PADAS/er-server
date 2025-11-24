#!/bin/sh
. $(dirname "$0")/wait_for.sh
wait_for $API_HOST $API_PORT

. $(dirname "$0")/django_common_startup.sh

WORKERS=2

# Redirect stderr to stdout to keep the log level info in gcp cloud logging
uv run celery --app das_server worker -Q realtime_p1,realtime_p2,realtime_p3,default,maintenance -l info -c $WORKERS --without-gossip -n default 2>&1
