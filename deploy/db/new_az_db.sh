#!/bin/bash
# WARNING: Used to populate dev instances. Review script security before using in production

if [ -z "$1" ]
  then
    echo "Must specify DB name"
    exit 1
fi

DB_NAME="$1"
DB_OWNER="$1"
DB_USER="$1_user"

# create a 32 char random password without dashes
# will use a RNG if present, otherwise its based off time 
RANDOM_UUID="uuidgen | tr -d '-'"
DB_OWNER_PWD=`eval ${RANDOM_UUID}`
RANDOM_UUID2="uuidgen | tr -d '-'"
DB_USER_PWD=`eval ${RANDOM_UUID2}`

# dump it to a json file
DB_DATA="{\"$DB_OWNER\":\""$DB_OWNER_PWD"\", \"$DB_USER\":\""$DB_USER_PWD"\", \"db_name\":\""$DB_NAME"\"}" 
echo -e $DB_DATA

