#!/bin/sh -e

SECRET_PATH=/etc/secrets
SSL_PATH=/etc/ssl

echo "$SSL_SECRET" > $SSL_PATH/ssl.key

HASHED_PASSWORD=$(openssl passwd -apr1 "$ELASTIC_BASIC_AUTH_PASSWORD")
echo "logger:$HASHED_PASSWORD" > /etc/nginx/passwords


/usr/sbin/nginx -g 'daemon off;'
