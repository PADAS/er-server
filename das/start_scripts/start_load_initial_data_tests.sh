#!/bin/sh
. $(dirname "$0")/wait_for.sh
wait_for $DB_HOST $DB_PORT

. $(dirname "$0")/django_common_startup.sh

python3 manage.py loaddata initial_admin_tests initial_groups initial_eventdata initial_dev_map initial_features initial_tilelayers event_data_model
