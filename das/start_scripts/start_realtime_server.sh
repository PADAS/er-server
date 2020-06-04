#!/bin/sh
. $(dirname "$0")/wait_for.sh
wait_for $API_HOST $API_PORT

python3 manage.py collectstatic --no-input

export EVENTLET_SHOULDPATCH=True

# Override GUNICORN_CMD_ARGS at deployment if desired.
# Keep in mind that the flags specified below, when running gunicorn, take
# precedence.
export GUNICORN_CMD_ARGS=${GUNICORN_CMD_ARGS:-"--bind 0.0.0.0:8000 --worker-class eventlet --timeout=90 --log-level=info"}

echo "Notice GUNICORN_CMD_ARGS: ${GUNICORN_CMD_ARGS}"

gunicorn das_server.rt_wsgi --name das_rt -w 1
