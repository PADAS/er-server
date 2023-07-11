#!/bin/sh
. $(dirname "$0")/wait_for.sh
wait_for $API_HOST $API_PORT

. $(dirname "$0")/django_common_startup.sh

celery --app das_server worker -Q analyzers,realtime_p1,realtime_p2,realtime_p3 -l info -c 2 --without-gossip -n analyzers 
