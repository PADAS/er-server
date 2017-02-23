
FROM ubuntu:16.04
MAINTAINER Matt Korwel, mattko@vulcan.com

RUN apt-get update \
    && apt-get install -y \
    build-essential \
    software-properties-common \
    ca-certificates \
    gcc \
    wget \
    && apt-get autoremove \
    && apt-get clean

RUN if [ ! -e /usr/lib/libproj.so ]; then \
  cd /opt; wget http://download.osgeo.org/proj/proj-4.9.2.tar.gz; tar -xzvf proj-4.9.2.tar.gz; cd proj-4.9.2; ./configure --prefix=/usr; make; make install; fi

RUN if [ ! -e /usr/lib/libgdal.so ]; then \
   cd /opt; wget http://download.osgeo.org/gdal/1.11.4/gdal-1.11.4.tar.gz; tar -xzvf gdal-1.11.4.tar.gz; cd gdal-1.11.4; ./configure --prefix=/usr; make; make install; fi

RUN if [ ! -e /usr/local/lib/libgeos_c.so ]; then \
    cd /opt; wget http://download.osgeo.org/geos/geos-3.5.0.tar.bz2; tar -xjf geos-3.5.0.tar.bz2; cd geos-3.5.0; ./configure; make; make install; fi
