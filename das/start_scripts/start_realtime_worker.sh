#!/bin/sh
. $(dirname "$0")/wait_for.sh
wait_for $API_HOST $API_PORT

python3 cfgloader.py
python3 manage.py collectstatic --no-input
celery -A das_server worker -Q realtime_p1,realtime_p2,realtime_p3 -l info -c 15 -P gevent --without-gossip -n priority
