#!/bin/sh
. $(dirname "$0")/wait_for.sh
wait_for $DB_HOST $DB_PORT

. $(dirname "$0")/django_common_startup.sh

# can't run a migration here, because the API pod coming up is already performing a migration
# maybe we should wait for that to finish. Could loop in showmigrations until all migrations are done.
#python3 manage.py migrate
python3 manage.py loaddata initial_admin_tests initial_groups initial_eventdata initial_dev_map initial_features initial_tilelayers event_data_model
