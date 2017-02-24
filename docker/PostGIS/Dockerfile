# Database
# https://docs.djangoproject.com/en/1.8/ref/settings/#databases
# we use postgis, create the db from the spatial db template
# CREATE DATABASE dasdb ENCODING 'utf8';
# \c dasdb;
# CREATE EXTENSION postgis;
# CREATE EXTENSION postgis_topology;

FROM mdillon/postgis
MAINTAINER MAtt Korwel, mattko@vulcan.com

ENV POSTGRES_USER das
ENV POSTGRES_PASSWORD password

ADD docker/PostGIS/init.sql /docker-entrypoint-initdb.d/