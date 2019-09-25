#!/bin/sh
. $(dirname "$0")/wait_for.sh
wait_for $DB_HOST $DB_PORT

pip3 install -r /workspace/dependencies/requirements-ci.txt -f /workspace/dependencies/wheelhouse
python3 manage.py test
