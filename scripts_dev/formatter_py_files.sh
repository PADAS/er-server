#!/bin/bash

if test -f "$1"; then
    typeFile=${1: -3}

    if [ "$typeFile" == ".py" ]; then
        echo "Runing autoflake for file $1"
        autoflake --in-place --remove-all-unused-imports --remove-unused-variables $1
        echo ""

        echo "Running isort for file $1"
        isort $1
        echo ""

        echo "Running autopep8 for file $1"
        autopep8 --in-place $1
        echo ""
    else
        echo "Format file $typeFile not allowed"
    fi

else
    echo "File does not exits on path $1"
    echo ""
fi
