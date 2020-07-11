#!/bin/sh
. /startup/wait_for.sh
wait_for $API_HOST $API_PORT

python3 beat_liveness.py