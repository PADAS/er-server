#!/bin/sh

WEB_SERVICE_NAME=${WEB_SERVICE_NAME-web}

if ! grep -q "upstream web_server" /etc/nginx/sites-available/default.conf; then
  (echo ""; echo "upstream web_server{ server $WEB_SERVICE_NAME:9000; }") >> /etc/nginx/sites-available/default.conf
fi

SSL_PATH=/etc/ssl

if [ -v $BUNDLE_CRT ]; then
    echo $BUNDLE_CRT > $SSL_PATH/bundle.crt
    echo $PAMDAS_ORG_PRIVATE_KEY_PEM > $SSL_PATH/pamdas.org-private-key.pem
fi

/usr/sbin/nginx -c /etc/nginx/nginx.conf -g "daemon off;"