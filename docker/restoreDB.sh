#!/bin/bash
set -e

if [ $# -eq 0 ]; then
    echo "This script is intended to restore a backup of postgres to a running postgres container"
    echo "USAGE:"
    echo "  1: backup file = required path to a backup file"
    exit 1
fi

if [ -z  "$(docker ps | grep postgres)" ]; then
    echo "postgres must be running to restore into postgres"
    echo "Run docker-compose up -d postgres first, then rerun this script"
    exit 1
fi

BACKUP=${1}

echo "Copying backup into container..."
docker cp $BACKUP das_postgres:/backup.compressed

echo "Dropping db..."
docker exec das_postgres dropdb --if-exists --username=postgres das

echo "Beginning restore..."
docker exec das_postgres pg_restore --create --dbname=postgres --username=postgres /backup.compressed

echo "Restore complete, cleaning up..."
docker exec das_postgres rm /backup.compressed

echo "Success! :)"