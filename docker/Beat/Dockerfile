FROM das/api

WORKDIR /var/www/das
CMD ["celery", "-A das_server", "beat", "-l info", "-s /tmp/celerybeat-schedule"]
