#!/bin/sh

. $(dirname "$0")/../start_scripts/wait_for.sh
wait_for $DB_HOST $DB_PORT

export PYTHONPATH=$(dirname "$0"):$PYTHONPATH

python3 -m pip install -r /workspace/dependencies/requirements-dev.txt \
   --find-links /workspace/dependencies/wheelhouse/ --upgrade

python3 manage.py test --keepdb --settings=unittest_settings
