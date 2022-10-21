#!/bin/sh
. $(dirname "$0")/wait_for.sh
wait_for $DB_HOST $DB_PORT

. $(dirname "$0")/django_common_startup.sh

pip3 install -r /workspace/dependencies/requirements-dev.txt -f /workspace/dependencies/wheelhouse
python3 manage.py test
