#!/bin/bash

# Run all the things

# API Unit Tests
docker/managelocal.sh test --noinput
unitTest=$?


echo "=================="

if [[ $unitTest -ne 0 ]]; then
    echo "Unit tests failed";
else
    echo "Unit tests passed";
fi


echo "=================="
