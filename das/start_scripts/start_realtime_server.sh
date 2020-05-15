#!/bin/sh
. $(dirname "$0")/wait_for.sh
wait_for $API_HOST $API_PORT

python3 manage.py collectstatic --no-input

export EVENTLET_SHOULDPATCH=True
if [ "$DEV" = "True" ]; then
    gunicorn -k eventlet -w 1 das_server.rt_wsgi --log-level=debug --bind=0.0.0.0:8000 --timeout=90
else
    gunicorn -k eventlet -w 1 das_server.rt_wsgi --bind=0.0.0.0:8000 --timeout=90
fi

