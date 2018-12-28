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
# will use a RNG if present, otherwise its based off time - uuids are good for
# uniqueness, but are sometimes easily guessable, so buyer beware...
RANDOM_UUID="uuidgen | tr -d '-'"
DB_OWNER_PWD=`eval ${RANDOM_UUID}`

# dump credential data to a json filea before creation
DB_DATA="{\"user\": \"$DB_OWNER\", \"password\": \""$DB_OWNER_PWD"\", \"db_name\":\""$DB_NAME"\"}" 
echo -e $DB_DATA > $DB_NAME.json 

psql -h $DB_HOST -U $DB_ADMIN postgres -v db_owner="$DB_OWNER" -v db_passwd="$DB_OWNER_PWD"  -v db_name="$DB_NAME" -f ./new_prod_db_azure.sql --set ON_ERROR_STOP=on

