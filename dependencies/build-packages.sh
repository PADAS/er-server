#!/bin/bash

# build in a docker container
    # docker run -it -w="/workspace" -v ~/projects/er/das/dependencies/:/workspace ubuntu:18.04 bash

PYTHON_PACKAGES="python3.7 python3.7-dev python3.7-distutils"
apt-get update && apt-get install --no-install-recommends -yq software-properties-common \
     && add-apt-repository ppa:deadsnakes/ppa && apt-get update \
     && apt-get install -yq --no-install-recommends ${PYTHON_PACKAGES} 

apt-get install -y build-essential \
                 software-properties-common \
                 ca-certificates \
                 gcc \
                 autoconf \
                 zip \
                 checkinstall \
                 wget \
                 pkg-config \
                 libtiff5-dev \
                 libcurl4-openssl-dev \
                 sqlite3 libsqlite3-dev \

update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.7 4
wget https://bootstrap.pypa.io/get-pip.py
python3 get-pip.py
python3 -m pip install pip --upgrade ; pip3 install pyopenssl setuptools wheel


arch=$(uname -i)
if [[ $arch == x86_64* ]]; then
    arch_name="amd64"
elif  ([[ $arch == arm* ]] || [[ $arch == aarch* ]]) ; then
    arch_name="arm64"
fi

cp_ver="cp37"

wget http://download.osgeo.org/geos/geos-3.9.1.tar.bz2; tar -xjf geos-3.9.1.tar.bz2
cd geos-3.9.1

# It's likely this 3.9.1 version of geos will report an invalid version. 
# So before running make, fix the GEOSversion function.
#
# Ex. In file capi/geos_ts_c.cpp, edit this:
#
#    const char* GEOSversion()
#    {
#       static char version[256];
#       /* sprintf(version, "%s " GEOS_REVISION, GEOS_CAPI_VERSION); */
#       return GEOS_CAPI_VERSION;  <-- This is what you need to return.
#    }
sed -i -e 's/return version/return GEOS_CAPI_VERSION/' capi/geos_ts_c.cpp

./configure; make; checkinstall -y;
cd ..
cp geos-3.9.1/geos_3.9.1-1_${arch_name}.deb ./geos_3.9.1-1_${cp_ver}_${arch_name}.deb
#rm -rf geos-3.9.1
ldconfig

wget http://download.osgeo.org/proj/proj-7.2.1.tar.gz; tar -xzvf proj-7.2.1.tar.gz; cd proj-7.2.1; ./configure --prefix=/usr; make; checkinstall -y;
cd ..
cp proj-7.2.1/proj_7.2.1-1_${arch_name}.deb ./proj_7.2.1-1_${cp_ver}_${arch_name}.deb
#rm -rf proj-7.2.1
ldconfig

wget http://download.osgeo.org/gdal/3.4.1/gdal-3.4.1.tar.gz; tar -xzvf gdal-3.4.1.tar.gz; cd gdal-3.4.1; ./configure --prefix=/usr --with-python=/usr/bin/python3.7 --with-geos=/usr/local/bin/geos-config --with-proj=/usr; make; checkinstall -y;
cd ..
cp gdal-3.4.1/gdal_3.4.1-1_${arch_name}.deb ./gdal_3.4.1-1_${cp_ver}_${arch_name}.deb
#rm -rf gdal-3.4.1

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
