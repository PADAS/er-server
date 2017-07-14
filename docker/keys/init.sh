#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
docker login -u _json_key -p "$(cat $DIR/pull.json)" https://gcr.io