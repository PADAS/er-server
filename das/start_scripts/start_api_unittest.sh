#!/bin/sh
. $(dirname "$0")/wait_for.sh
wait_for $DB_HOST $DB_PORT

. $(dirname "$0")/django_common_startup.sh

uv sync --no-install-project --group dev --find-links /das/dependencies/wheelhouse
python manage.py test
