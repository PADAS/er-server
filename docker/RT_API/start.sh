#!/bin/sh
. /startup/wait_for.sh
wait_for $API_HOST $API_PORT

python3 cfgloader.py
python3 manage.py collectstatic --no-input

if [ "$DEV" = "True" ]; then
    gunicorn -k eventlet -w 1 das_server.rt_wsgi --log-level=debug --bind=0.0.0.0:8000
else
    gunicorn -k eventlet -w 1 das_server.rt_wsgi --bind=0.0.0.0:8000
fi

