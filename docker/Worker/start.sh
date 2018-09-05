#!/bin/sh
. /startup/wait_for.sh
wait_for $API_HOST $API_PORT

python3 manage.py collectstatic --no-input
celery -A das_server worker -l debug
