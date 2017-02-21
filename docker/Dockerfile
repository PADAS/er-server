FROM ubuntu:16.04


RUN apt-get update && apt-get install -y \
        binutils \
        libproj-dev \
        gdal-bin \
        libgeos-dev \
        libpq-dev \
        python3-dev \
        libgdal-dev \
        python-pip \
        git
ENV CPLUS_INCLUDE_PATH /usr/include/gdal 
ENV C_INCLUDE_PATH /usr/include/gdal
RUN pip install --upgrade pip

VOLUME /code
WORKDIR /code
ADD ./requirements.txt /code/requirements.txt
ADD ./das /code/das
RUN pip install -r /code/requirements.txt
