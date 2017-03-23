#!/bin/sh -x

HOST=postgis
PORT=5432

wait_for()
{
    start_ts=$(date +%s)
    while :
    do
        bash -c '(echo > /dev/tcp/$1/$2) >/dev/null 2>&1' -- $HOST $PORT
        result=$?
        if [ $result -eq 0 ]; then
            end_ts=$(date +%s)
            echo "$HOST:$PORT is available after $((end_ts - start_ts)) seconds"
            break
        fi
        sleep 1
    done
    return $result
}

wait_for

cd /var/www/das
export DJANGO_SETTINGS_MODULE=das_server.local_settings_docker
python3 manage.py migrate
python3 manage.py runserver 0.0.0.0:8000