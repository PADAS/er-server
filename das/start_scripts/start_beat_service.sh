#!/bin/sh
. $(dirname "$0")/wait_for.sh
wait_for $API_HOST $API_PORT
celery -A das_server beat -l info -s /tmp/celerybeat-schedule
