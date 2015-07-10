DROP DATABASE IF EXISTS :db_name;
CREATE DATABASE :db_name ENCODING 'utf8';
\c :db_name;
CREATE EXTENSION postgis;
CREATE EXTENSION postgis_topology;
