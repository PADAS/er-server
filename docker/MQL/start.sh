#!/bin/sh
. /startup/wait_for.sh
wait_for $API_HOST $API_PORT

python3 manage.py message_queue_listeners