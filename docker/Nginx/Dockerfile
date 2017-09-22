FROM nginx
MAINTAINER Chris Doehring, chrisdo@vulcan.com & Matt Korwel, mattko@vulcan.com

ADD ./nginx.conf /etc/nginx/
ADD ./default.conf /etc/nginx/sites-available/default.conf
RUN mkdir -p /etc/nginx/sites-enabled
RUN ln -s /etc/nginx/sites-available/default.conf /etc/nginx/sites-enabled/
ADD ./start.sh /startup/start.sh
RUN chmod +x /startup/start.sh

ENTRYPOINT ["/startup/start.sh"]

EXPOSE 8000