#!/usr/bin/env bash

if [[ "$(er list-tenants | jq -r '.[].name' | tr '\n' ' ')" == *"$1"* ]]; then
    exit 0
fi

exit 1
