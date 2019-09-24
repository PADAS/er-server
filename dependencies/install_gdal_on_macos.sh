#!/bin/bash
#
# If you're working in MacOS and you want to install python bindings for GDAL, you might find
# that it does not work simply using pip install.
#
# Your experience might vary, but this script helps you with an alternative method.
#
# Here are some steps to follow:
#
#  1. Install gdal (if you haven't already) by:
#     `brew install gdal`
#     As of this writing you'll get a version somewhere near 2.3.2

#  2. Run this script; be sure to do so within a virtual environment where you plan to use GDAL.

#  3. Avoid re-installing python binding with pip.
#     Typically this means you'll want to comment-out the gdal line within your requirements*.txt
#     files before running them through pip.

#  4. Install your remaining dependencies normally (ex. pip install -r requirements.txt)
#
# * If you wind up accidentally asking pip to install GDAL bindings, it's OK. You can go back to
#   step 2 in and carry-on.

if [[ $(which  gdal-config) ]]
then
  echo "gdal is installed at $(gdal-config --prefix)"
else
   echo "I can't find gdal installed. Use 'brew install gdal' and then come back to run this script."
  exit
fi

GDAL_VERSION=$(gdal-config --version)
pip download gdal==${GDAL_VERSION}
tar zxvf GDAL-${GDAL_VERSION}.tar.gz
cd GDAL-${GDAL_VERSION}
#dirname $(dirname $(greadlink -f $(which gdal-config)))
export GDAL_HOME=$(gdal-config --prefix)

python setup.py build_ext --gdal=config=$GDAL_HOME/bin/gdal-config \
    --library-dirs=$GDAL_HOME/lib --libraries=gdal --include-dirs=$GDAL_HOME/include
python setup.py build
python setup.py install
cd ..
#rm -r GDAL-${GDAL_VERSION}

