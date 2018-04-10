ARG base_tag=latest
FROM gcr.io/padas-app/app:${base_tag}

RUN pip3 install django-extensions
RUN pip3 install jupyter
RUN pip3 install joblib

ADD ./notebook_settings.py /var/www/app/das_server/notebook_settings.py
ADD ./jupyter_notebook_config.json /root/.jupyter/jupyter_notebook_config.json
ADD ./start.sh /var/www/app/start.sh
