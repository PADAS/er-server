#!/bin/sh
. $(dirname "$0")/wait_for.sh
wait_for $DB_HOST $DB_PORT

python3 manage.py migrate --no-input

. $(dirname "$0")/django_common_startup.sh

# Override GUNICORN_CMD_ARGS at deployment if desired.
# Keep in mind that the flags specified below, when running gunicorn, take 
# precedence.
export GUNICORN_CMD_ARGS=${GUNICORN_CMD_ARGS:-"--bind 0.0.0.0:8000 --workers 4 --threads 4 --worker-class gthread"}

echo "Notice GUNICORN_CMD_ARGS: ${GUNICORN_CMD_ARGS}"

gunicorn das_server.wsgi --name das \
    --limit-request-line 6000 \
    --worker-tmp-dir /dev/shm \
    --log-file - 
