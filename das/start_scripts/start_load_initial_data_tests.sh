#!/bin/sh
# Check arguments
if [ $# -ne 1 ]; then
  echo "Usage: ./start_load_initial_data_tests.sh <domain>"
  exit 1
fi

TENANT_DOMAIN=$1

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

  i=`expr $i + 1`
done

if ! python3 manage.py migrate --check ; then
    echo "Migration are not complete"
    exit 1
fi
python3 manage.py loaddata_with_tenant --tenant_domain "$TENANT_DOMAIN" initial_admin_tests initial_groups initial_eventdata initial_dev_map initial_features initial_tilelayers event_data_model
