#!/bin/sh -e

SECRET_PATH=/etc/secrets
SSL_PATH=/etc/ssl

echo "$SSL_KEY" > $SSL_PATH/ssl.key
echo "$SSL_CERT" > $SSL_PATH/certificate.pem
echo "$SSL_CA" > $SSL_PATH/ca.pem

HASHED_PASSWORD=$(openssl passwd -apr1 "$ELASTIC_BASIC_AUTH_PASSWORD")
echo "$ELASTIC_BASIC_AUTH_USERNAME:$HASHED_PASSWORD" > /etc/nginx/passwords


/usr/sbin/nginx -g 'daemon off;'
