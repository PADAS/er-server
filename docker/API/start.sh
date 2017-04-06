#!/bin/sh
. ./wait_for.sh
wait_for

python3 manage.py migrate
python3 manage.py loaddata initial_admin initial_eventdata initial_dev_map
python3 manage.py runserver 0.0.0.0:8000