#!/bin/sh

if [ ! -z "$REACT_APP_MOCK_API_URL" ]; then
    rm -rf /etc/nginx/sites-enabled/default.conf
    ln -f -s /etc/nginx/sites-available/dev.conf /etc/nginx/sites-enabled/default.conf
else
    rm -rf /etc/nginx/sites-enabled/default.conf
    ln -f -s /etc/nginx/sites-available/default.conf /etc/nginx/sites-enabled/
fi

WEB_SERVICE_NAME=${WEB_SERVICE_NAME-web}

if ! grep -q "upstream web_server" /etc/nginx/sites-available/default.conf; then
  (echo ""; echo "upstream web_server{ server $WEB_SERVICE_NAME:9000; }") >> /etc/nginx/sites-available/default.conf
fi

if ! grep -q "upstream web_server" /etc/nginx/sites-available/dev.conf; then
  (echo ""; echo "upstream web_server{ server $WEB_SERVICE_NAME:9000; }") >> /etc/nginx/sites-available/dev.conf
fi

SSL_PATH=/etc/ssl

if [ ! -z "$BUNDLE_CRT" ]; then
    echo "$BUNDLE_CRT" > $SSL_PATH/bundle.crt
    echo "$PAMDAS_ORG_PRIVATE_KEY_PEM" > $SSL_PATH/pamdas.org-private-key.pem
fi



/usr/sbin/nginx -c /etc/nginx/nginx.conf -g "daemon off;"
