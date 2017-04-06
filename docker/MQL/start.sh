#!/bin/sh
. ./wait_for.sh
wait_for

python3 manage.py message_queue_listeners