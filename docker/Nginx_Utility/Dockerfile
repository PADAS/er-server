FROM nginx
MAINTAINER SharedServices

RUN apt-get update && apt-get install openssl -y

ADD ./config/nginx.conf /etc/nginx/
ADD ./config/certificate.pem /etc/ssl/
ADD ./config/default.conf /etc/nginx/sites-available/default.conf
RUN mkdir -p /etc/nginx/sites-enabled
RUN ln -s /etc/nginx/sites-available/default.conf /etc/nginx/sites-enabled/

ADD ./start.sh /startup/start.sh
RUN chmod +x /startup/start.sh

ENTRYPOINT ["/startup/start.sh"]