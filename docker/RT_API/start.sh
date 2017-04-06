#!/bin/sh
. ./wait_for.sh
wait_for

python3 manage.py rtserver 0.0.0.0:8000