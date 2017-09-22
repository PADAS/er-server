#!/bin/sh
. /startup/wait_for.sh
wait_for $DB_HOST $DB_PORT

python3 manage.py test