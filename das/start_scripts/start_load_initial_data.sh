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

python3 manage.py create_tenant
python3 manage.py loaddata_with_tenant --tenant_domain "$TENANT_DOMAIN" initial_admin initial_groups initial_eventdata initial_dev_map initial_features initial_tilelayers event_data_model
