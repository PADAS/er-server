#!/bin/sh

. $(dirname "$0")/../start_scripts/wait_for.sh
wait_for $DB_HOST $DB_PORT

export PYTHONPATH=$(dirname "$0"):$PYTHONPATH

python3 -m pip install --upgrade keyrings.alt
python3 -m pip install -r /workspace/dependencies/requirements-dev.txt \
   --find-links /workspace/dependencies/wheelhouse/ --upgrade

export DJANGO_SETTINGS_MODULE=unittest_settings
pwd
pytest --create-db --junitxml=/testresults/result.xml das/accounts/tests
