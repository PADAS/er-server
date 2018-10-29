#!/bin/bash
# WARNING: Used to populate us dev instances. Review script security before using in production

if [ -z "$1" ]
  then
    echo "Must specify DB name"
    exit 1
fi

DB_HOST="das-postgres-us-azure.postgres.database.azure.com"
DB_ADMIN="postgres@das-postgres-us-azure"
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
echo -e $DB_DATA > 

psql -h $DB_HOST -U $DB_ADMIN -v ownerpw="'$ownerpw'" -v userpw="'$userpw'" -v db_name="$db_name" -f .\new_prod_db.sql --set ON_ERROR_STOP=on

