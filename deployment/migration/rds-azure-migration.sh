#!/bin/sh
DB_HOSTNAME=apn-bangweulu-das-db.cmv9k8w7frbn.eu-central-1.rds.amazonaws.com
DB_NAME=bangweulu

pg_dump -s -h $DB_HOSTNAME -U postgres das > $DB_NAME.schema
sed -i '/rdsadmin/d' $DB_NAME.schema
OWNER_CHANGE="s/postgres/bangweulu/g"
sed -i $OWNER_CHANGE $DB_NAME.schema
pg_dump --data-only --no-privileges --no-owner -h $DB_HOSTNAME -U postgres -Fc -Z 9 -f $DB_NAME.dump das
