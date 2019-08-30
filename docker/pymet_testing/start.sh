#!/bin/sh
. /startup/wait_for.sh
wait_for $DB_HOST $DB_PORT

pip3 install -r /workspace/dependencies/requirements-ci.txt -f /workspace/dependencies/wheelhouse
/bin/bash

