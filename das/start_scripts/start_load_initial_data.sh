#!/bin/sh
# Check arguments
if [ $# -ne 1 ]; then
  echo "Usage: ./start_load_initial_data.sh <domain>"
  exit 1
fi

TENANT_DOMAIN=$1

. $(dirname "$0")/wait_for.sh
wait_for $DB_HOST $DB_PORT

. $(dirname "$0")/django_common_startup.sh



python manage.py create_tenant $TENANT_DOMAIN

if python manage.py runscript tenant_has_initial_data --script-args "$TENANT_DOMAIN" ; then
  echo "There is data in the db already, exiting out"
  exit 0
fi
echo "Load $TENANT_DOMAIN initial data"

python manage.py loaddata_with_tenant --tenant_domain "$TENANT_DOMAIN" initial_admin initial_groups initial_eventdata initial_dev_map initial_features initial_tilelayers event_data_model
