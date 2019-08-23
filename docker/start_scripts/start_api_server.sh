#!/bin/sh
. /startup/wait_for.sh
wait_for $DB_HOST $DB_PORT

python3 cfgloader.py
python3 manage.py migrate --no-input
python3 manage.py collectstatic --no-input
python3 manage.py loaddata initial_admin initial_groups initial_eventdata initial_dev_map initial_features initial_tilelayers event_data_model

if [ "$DEV" = "True" ]; then
    python3 manage.py runserver 0.0.0.0:8000 --noreload
else
    python3 manage.py runserver 0.0.0.0:8000 --noreload
fi
