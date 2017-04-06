#!/bin/sh
. ./wait_for.sh

wait_for

celery -A das_server worker -l info