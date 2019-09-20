#!/bin/sh
. $(dirname "$0")/wait_for.sh
wait_for $API_HOST $API_PORT

python3 cfgloader.py
python3 manage.py message_queue_listeners
