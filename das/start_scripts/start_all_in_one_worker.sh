#!/bin/sh
. $(dirname "$0")/wait_for.sh
wait_for $API_HOST $API_PORT

. $(dirname "$0")/django_common_startup.sh
 
WORKERS=10

celery worker -A das_server -Q realtime_p1,realtime_p2,realtime_p3,analyzers,default,maintenance -l info -c $WORKERS --without-gossip -n all-in-one 
