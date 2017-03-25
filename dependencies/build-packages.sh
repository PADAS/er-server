apt-get install  build-essential \
                 software-properties-common \
                 ca-certificates \
                 gcc \
                 wget

wget http://download.osgeo.org/proj/proj-4.9.2.tar.gz; tar -xzvf proj-4.9.2.tar.gz; cd proj-4.9.2; ./configure --prefix=/usr; make; checkinstall;
cp proj-4.9.2/proj_4.9.2-1_amd64.deb .
rm -rf proj-4.9.2

wget http://download.osgeo.org/gdal/1.11.4/gdal-1.11.4.tar.gz; tar -xzvf gdal-1.11.4.tar.gz; cd gdal-1.11.4; ./configure --prefix=/usr; make; checkinstall;
cp gdal-1.11.4/gdal_1.11.4-1_amd64.deb .
rm -rf gdal-1.11.4

wget http://download.osgeo.org/geos/geos-3.5.0.tar.bz2; tar -xjf geos-3.5.0.tar.bz2; cd geos-3.5.0; ./configure; make; checkinstall;
cp geos-3.5.0/geos-3.5.0-1_amd64.deb .
rm -rf geos-3.5.0

# RUN if [ ! -e /usr/lib/libproj.so ]; then \
#   cd /opt; wget http://download.osgeo.org/proj/proj-4.9.2.tar.gz; tar -xzvf proj-4.9.2.tar.gz; cd proj-4.9.2; ./configure --prefix=/usr; make; make install; fi

# RUN if [ ! -e /usr/lib/libgdal.so ]; then \
#   cd /opt; wget http://download.osgeo.org/gdal/1.11.4/gdal-1.11.4.tar.gz; tar -xzvf gdal-1.11.4.tar.gz; cd gdal-1.11.4; ./configure --prefix=/usr; make; make install; fi

# RUN if [ ! -e /usr/local/lib/libgeos_c.so ]; then \
#    cd /opt; wget http://download.osgeo.org/geos/geos-3.5.0.tar.bz2; tar -xjf geos-3.5.0.tar.bz2; cd geos-3.5.0; ./configure; make; make install; fi
