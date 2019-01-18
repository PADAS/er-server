#!/bin/bash
# WARNING: Used to populate us dev instances. Review script security before using in production

if [ $# -ne 3 ]
  then
    echo "Usage $0 dbshost dbsadmin dbname"
    exit 1
fi

DB_HOST="$1"
DB_ADMIN="$2"
DB_NAME="$3"
DB_OWNER="$3"

# create a 32 char random password without dashes
# switched from uuidgen to openssl, to get upper and lower chars
RANDOM_UUID="openssl rand -base64 18"
DB_OWNER_PWD=`eval ${RANDOM_UUID}`

# dump credential data to a json filea before creation
DB_DATA="{\"user\": \"$DB_OWNER\", \"password\": \""$DB_OWNER_PWD"\", \"db_name\":\""$DB_NAME"\", \"db_host\":\""$DB_HOST"\"}" 
echo -e $DB_DATA > $DB_NAME.json 

psql -h $DB_HOST -U $DB_ADMIN postgres -v db_owner="$DB_OWNER" -v db_passwd="$DB_OWNER_PWD"  -v db_name="$DB_NAME" -f ./new_prod_db_azure.sql --set ON_ERROR_STOP=on -W

