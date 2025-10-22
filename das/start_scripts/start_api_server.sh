#!/bin/bash
. $(dirname "$0")/wait_for.sh
wait_for $DB_HOST $DB_PORT


function app_has_migrated () {
    local app=$1
    local pattern=$2
    uv run python3 manage.py showmigrations $app --skip-checks | grep -q "$pattern" && return 0 || return 1
}

function app_in_maintenance_mode () {
    uv run python3 manage.py maintenancemode status --skip-checks | grep -q "Maintenance mode is enabled" && return 0 || return 1
}

function app_has_pending_migrations () {
    uv run python3 manage.py showmigrations --skip-checks | grep -q "\[ \]" && return 0 || return 1
}

if [[ "${MIGRATIONS_ONLY}" == "True" ]]; then

  if ! app_has_pending_migrations ; then
    echo "No pending migrations, exiting"
    if app_in_maintenance_mode ; then
      uv run python3 manage.py maintenancemode disable
      echo "Maintenance mode has been disabled"
    fi
    exit 0
  fi

  if app_in_maintenance_mode ; then
    echo "Maintenance mode is already enabled, exiting"
    exit 0
  fi

  if app_has_migrated core '\[ \].0008_migrate'; then
      echo "settings override"
      # we haven't migrated to the core oauth tables yet
      if ! uv run python3 manage.py migratewithlock --no-input --settings=das_server.local_settings_oauth_migration; then
          echo "Failed to run migratewithlock command, exiting"
          exit 1
      fi
  else
      echo "no override of settings"
      # db has been migrated past core oauth tables
      if ! uv run python3 manage.py migratewithlock --no-input; then
          echo "Failed to run migratewithlock command, exiting"
          exit 1
      fi
  fi

  uv run python3 manage.py maintenancemode disable
  echo "Maintenance mode has been disabled"

  echo "MIGRATIONS_ONLY is set to True, exiting"
  exit 0
fi


. $(dirname "$0")/django_common_startup.sh

# Override GUNICORN_CMD_ARGS at deployment if desired.
# Keep in mind that the flags specified below, when running gunicorn, take
# precedence.
GUNICORN_CMD_ARGS=${GUNICORN_CMD_ARGS:-"--workers 3 --threads 2 --worker-class gthread --max-requests 20000 --max-requests-jitter 500 --timeout 60 --graceful-timeout 40 --keep-alive 10"}
export GUNICORN_CMD_ARGS

echo "Notice GUNICORN_CMD_ARGS: ${GUNICORN_CMD_ARGS}"

uv run gunicorn das_server.wsgi --name das \
    --bind 0.0.0.0:8000 \
    --limit-request-line 8190 \
    --worker-tmp-dir /dev/shm \
    -c das_server/gunicorn.conf.py \
    --log-level info \
    --error-logfile - \
    --capture-output 2>&1
