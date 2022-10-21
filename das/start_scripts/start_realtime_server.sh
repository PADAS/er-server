#!/bin/sh
. $(dirname "$0")/wait_for.sh
wait_for $API_HOST $API_PORT

. $(dirname "$0")/django_common_startup.sh

export EVENTLET_SHOULDPATCH=True

# Override GUNICORN_CMD_ARGS at deployment if desired.
# Keep in mind that the flags specified below, when running gunicorn, take
# precedence.
GUNICORN_CMD_ARGS=${REALTIME_GUNICORN_CMD_ARGS:-"--worker-class eventlet -w 1 --timeout=90 --log-level=info"}
export GUNICORN_CMD_ARGS

echo "Notice GUNICORN_CMD_ARGS: ${GUNICORN_CMD_ARGS}"

gunicorn das_server.rt_wsgi --name das_rt --worker-tmp-dir /dev/shm --bind 0.0.0.0:8000 
