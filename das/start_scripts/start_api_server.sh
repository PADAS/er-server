#!/bin/bash
. $(dirname "$0")/wait_for.sh
wait_for $DB_HOST $DB_PORT


function app_has_migrated () {
    local app=$1
    local pattern=$2
    python3 manage.py showmigrations $app --skip-checks | grep -q "$pattern" && return 0 || return 1
}

if app_has_migrated oauth2_provider '\[X\].0001_initial' && app_has_migrated core '\[ \].0008_migrate'; then
  echo "settings override"
  # partially migrated db, just missing the migration to core oauth tables
  python3 manage.py migrate --no-input --settings=das_server.local_settings_oauth_migration
else
  echo "no override of settings"
  # for a new database with no migrations, we do a clean migrate with no need to fixup oauth2_provider
  python3 manage.py migrate --no-input
fi

. $(dirname "$0")/django_common_startup.sh

# Override GUNICORN_CMD_ARGS at deployment if desired.
# Keep in mind that the flags specified below, when running gunicorn, take
# precedence.
GUNICORN_CMD_ARGS=${GUNICORN_CMD_ARGS:-"--workers 1 --threads 4 --worker-class gthread --max-requests 500000 --max-requests-jitter 500 --timeout 60"}
export GUNICORN_CMD_ARGS

echo "Notice GUNICORN_CMD_ARGS: ${GUNICORN_CMD_ARGS}"

gunicorn das_server.wsgi --name das \
    --bind 0.0.0.0:8000 \
    --limit-request-line 6000 \
    --worker-tmp-dir /dev/shm \
    --log-file -
