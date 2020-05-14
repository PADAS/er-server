#!/bin/sh
. $(dirname "$0")/wait_for.sh
wait_for $DB_HOST $DB_PORT

python3 manage.py migrate --no-input
python3 manage.py collectstatic --no-input

# Override GUNICORN_CMD_ARGS at deployment if desired.
# Keep in mind that the flags specified below, when running gunicorn, take 
# precedence.
export GUNICORN_CMD_ARGS=${GUNICORN_CMD_ARGS:-"--bind 0.0.0.0:8000 --workers 6"}

echo "Notice GUNICORN_CMD_ARGS: ${GUNICORN_CMD_ARGS}"

gunicorn das_server.wsgi --name das \
    --user www-data \
    --group www-data \
    --limit-request-line 6000 \
    --env DJANGO_SETTINGS_MODULE=das_server.local_settings_docker
