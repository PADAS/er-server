FROM nginx
MAINTAINER Chris Doehring, chrisdo@vulcan.com & Matt Korwel, mattko@vulcan.com

RUN apt-get update; apt-get install -y openssl
RUN apt-get update && apt-get install -y vim

ADD ./nginx.conf /etc/nginx/
ADD ./default.conf /etc/nginx/sites-available/default.conf
ADD ./prod.conf /etc/nginx/sites-available/dev.conf
RUN mkdir -p /etc/nginx/sites-enabled

ADD ./bundle.crt /etc/ssl/
ADD ./pamdas.org-private-key.pem /etc/ssl/

ADD ./start.sh /startup/start.sh
RUN chmod +x /startup/start.sh

ENTRYPOINT ["/startup/start.sh"]

EXPOSE 8000 443
