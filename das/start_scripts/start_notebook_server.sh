#!/bin/sh
. $(dirname "$0")/wait_for.sh
wait_for $DB_HOST $DB_PORT

# Install notebook-specific dependencies
uv add oauth2client django-extensions jupyterlab

# This writes a default password `dasdasdas`.
# TODO: Find a way to make this easily configurable.
JUPYTER_NOTEBOOK_CONFIG="
{
  \"NotebookApp\": {
    \"password\": \"sha1:b0099d6bbb90:070c01257ed3649f4be027f363516539be36ed4d\"
  }
}
"

mkdir -p /root/.jupyter
echo $JUPYTER_NOTEBOOK_CONFIG > /root/.jupyter/jupyter_notebook_config.json

. $(dirname "$0")/django_common_startup.sh

export PYTHONPATH=/var/www/app:$PYTHONPATH
uv run python3 manage.py shell_plus --notebook --settings=das_server.notebook_settings
