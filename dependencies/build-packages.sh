#!/usr/bin/env bash

apt-get update -y
apt-get install -y build-essential \
                 software-properties-common \
                 ca-certificates \
                 gcc \
                 autoconf \
                 zip \
                 checkinstall \
                 python3-dev \
                 wget


wget http://download.osgeo.org/geos/geos-3.6.1.tar.bz2; tar -xjf geos-3.6.1.tar.bz2; cd geos-3.6.1; ./configure; make; checkinstall -y;
cd ..
cp geos-3.6.1/geos_3.6.1-1_amd64.deb .
rm -rf geos-3.6.1
ldconfig

wget http://download.osgeo.org/proj/proj-4.9.3.tar.gz; tar -xzvf proj-4.9.3.tar.gz; cd proj-4.9.3; ./configure --prefix=/usr; make; checkinstall -y;
cd ..
cp proj-4.9.3/proj_4.9.3-1_amd64.deb .
rm -rf proj-4.9.3
ldconfig

wget http://download.osgeo.org/gdal/2.1.3/gdal-2.1.3.tar.gz; tar -xzvf gdal-2.1.3.tar.gz; cd gdal-2.1.3; ./configure --prefix=/usr --with-python=/usr/bin/python3 --with-geos=/usr/local/bin/geos-config --with-static-proj4=/usr/lib/libproj.a; make; checkinstall -y;
cd ..
cp gdal-2.1.3/gdal_2.1.3-1_amd64.deb .
rm -rf gdal-2.1.3

# RUN if [ ! -e /usr/lib/libproj.so ]; then \
#   cd /opt; wget http://download.osgeo.org/proj/proj-4.9.2.tar.gz; tar -xzvf proj-4.9.2.tar.gz; cd proj-4.9.2; ./configure --prefix=/usr; make; make install; fi

# RUN if [ ! -e /usr/lib/libgdal.so ]; then \
#   cd /opt; wget http://download.osgeo.org/gdal/1.11.4/gdal-1.11.4.tar.gz; tar -xzvf gdal-1.11.4.tar.gz; cd gdal-1.11.4; ./configure --prefix=/usr; make; make install; fi

# RUN if [ ! -e /usr/local/lib/libgeos_c.so ]; then \
#    cd /opt; wget http://download.osgeo.org/geos/geos-3.5.0.tar.bz2; tar -xjf geos-3.5.0.tar.bz2; cd geos-3.5.0; ./configure; make; make install; fi

# Best practice is to clean up packages before creating a docker image
#apt-get clean && rm -rf /var/lib/apt/lists/*

# The following 4 lines of code succeeds if gdal is compiled with geos correctly
#from osgeo import ogr
#p1 = ogr.CreateGeometryFromWkt('POINT(10 20)')
#p2 = ogr.CreateGeometryFromWkt('POINT(30 20)')
#u = p1.Union(p2)
