#!/bin/sh
. $(dirname "$0")/wait_for.sh
wait_for $DB_HOST $DB_PORT

python3 manage.py migrate --no-input
python3 manage.py collectstatic --no-input

if [ "$DEV" = "True" ]; then
    python3 manage.py runserver 0.0.0.0:8000
else
    python3 manage.py runserver 0.0.0.0:8000 --noreload
fi
