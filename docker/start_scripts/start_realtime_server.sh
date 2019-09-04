#!/bin/sh
. /startup/wait_for.sh
wait_for $API_HOST $API_PORT

python3 cfgloader.py
python3 manage.py collectstatic --no-input

if [ "$DEV" = "True" ]; then
    python3 manage.py rtserver 0.0.0.0:8000 --nothreading
else
    python3 manage.py rtserver 0.0.0.0:8000 --noreload --nothreading
fi

