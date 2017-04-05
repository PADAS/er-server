FROM das/api

WORKDIR /var/www/das

ENV EVENTLET_SHOULDPATCH=True

#CMD /usr/bin/gunicorn --worker-class eventlet rt_wsgi.py:application -w 1 -b :8000
CMD ["python3", "manage.py", "rtserver", "0.0.0.0:8000"]
EXPOSE 8000