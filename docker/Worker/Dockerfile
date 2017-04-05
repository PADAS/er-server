FROM das/api

WORKDIR /var/www/das
CMD ["celery", "-A das_server", "worker", "-l info"]