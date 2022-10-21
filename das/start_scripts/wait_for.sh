#!/bin/bash
wait_for()
{
    start_ts=$(date +%s)
    while :
    do
        bash -c '(echo > /dev/tcp/$1/$2) >/dev/null 2>&1' -- $1 $2
        result=$?
        if [ $result -eq 0 ]; then
            end_ts=$(date +%s)
            echo `date -u` " $1:$2 is available after $((end_ts - start_ts)) seconds"
            break
        fi
        sleep 1
        echo `date -u` " Waiting for $1:$2 ..."
    done
    return $result
}