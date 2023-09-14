#!/bin/sh
. $(dirname "$0")/wait_for.sh
wait_for $DB_HOST $DB_PORT

. $(dirname "$0")/django_common_startup.sh

i=0
while [ $i -le 100 ]
do
  if python3 manage.py migrate --check ; then
    echo "Migrations completed"
    break
  fi

  echo "Waiting for migrations to complete..."
  sleep 5

  i++
done

if ! python3 manage.py migrate --check ; then
    echo "Migration are not complete"
    exit 1
fi
python3 manage.py loaddata_with_tenant initial_admin_tests initial_groups initial_eventdata initial_dev_map initial_features initial_tilelayers event_data_model
