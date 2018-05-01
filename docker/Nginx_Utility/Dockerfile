FROM nginx
MAINTAINER SharedServices

ADD ./config/nginx.conf /etc/nginx/
ADD ./config/default.conf /etc/nginx/sites-available/default.conf
RUN mkdir -p /etc/nginx/sites-enabled
RUN ln -s /etc/nginx/sites-available/default.conf /etc/nginx/sites-enabled/

ENTRYPOINT ["/usr/sbin/nginx",  "-g", "daemon off;"]