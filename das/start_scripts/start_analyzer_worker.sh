#!/bin/sh
. $(dirname "$0")/wait_for.sh
wait_for $API_HOST $API_PORT

celery worker -A das_server -Q analyzers -l info -c 2 --without-gossip -n analyzers

