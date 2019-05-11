#!/bin/sh
. /startup/wait_for.sh
wait_for $API_HOST $API_PORT

python3 cfgloader.py
python3 manage.py collectstatic --no-input
celery -A das_server worker -Q default,maintenance -l info -c 10 -P gevent --without-gossip -n default
