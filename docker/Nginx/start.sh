#!/bin/sh

WEB_SERVICE_NAME=${WEB_SERVICE_NAME-web}

if ! grep -q "upstream web_server" /etc/nginx/default.conf; then
  (echo ""; echo "upstream web_server{ server $WEB_SERVICE_NAME:9000; }") >> /etc/nginx/default.conf
fi

/usr/sbin/nginx -c /etc/nginx/nginx.conf -g "daemon off;"