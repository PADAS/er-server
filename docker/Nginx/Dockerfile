FROM ubuntu:16.04
MAINTAINER Chris Doehring, chrisdo@vulcan.com & Matt Korwel, mattko@vulcan.com

RUN apt-get update \
    && apt-get install -y \
    nginx \
    && apt-get autoremove \
    && apt-get clean

VOLUME /workspace
WORKDIR /workspace

RUN rm -v /etc/nginx/nginx.conf
RUN rm -v /etc/nginx/sites-enabled/default
ADD ./nginx.conf /etc/nginx/

ENTRYPOINT ["/usr/sbin/nginx",  "-g", "daemon off;"]
EXPOSE 8000