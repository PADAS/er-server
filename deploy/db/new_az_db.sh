#!/bin/bash
# WARNING: Used to populate dev instances. Review script security before using in production

# create a 32 char random password
RANDOM_UUID="uuidgen | tr -d '-'"
DB_OWNER_PWD=`eval ${RANDOM_UUID}`
DB_USER_PWD=`eval ${RANDOM_UUID}`

# dump it to a json file
echo -e "{\"$DB_OWNER\":\""$DB_OWNER_PWD"\", \"$DB_USER\":\""$DB_USER_PWD"\", \"db_name\":\""$DB_NAME"\"}" 
echo $OWNER_PWD
echo $USER_PWD

