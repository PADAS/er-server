#!/bin/sh
. /startup/wait_for.sh
wait_for $API_HOST $API_PORT

celery -A das_server worker -l info