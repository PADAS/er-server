Project DAS - Domain Awareness System
=================================================================


Developer Setup
=================================================================
Requirements
-----------------------------------------------------------------

* Python 3.6
* Postgres 9.6

Coding Conventions
-----------------------------------------------------------------
* PEP 8 -- Style Guide for Python Code
* Spaces not tabs, 4 space indents
* Maximum line length less than 80
* Doc strings less than 72
* Line breaks before operators
* '' single quotes around strings as much as possible

Unit Testing
-----------------------------------------------------------------
* We use python unittest with Django unittest extensions
* Put tests in with each app
* python manage.py test --settings=das_server.local_settings


Development Environment Setup
----------------------------------------------------------------
We use Docker to develop, test and deploy DAS
* Install Docker for your operating system
* plan on using a common parent directory for cloning das and das-web repositories
  assume this is ./das
* Clone the das Github repo in ./das (git@github.com:PADAS/das.git)
* Clone the das-web Gihub repo in ./das (git@github.com:PADAS/das-web.git)
* start your favorite terminal window, cd to ./das/das
* build docker images for all services. this will also build and include das-web
  >docker-compose build
* once this successfully completes, run it
  >docker-compose up
* on success, the full stack is running, navigate to http://localhost:9000
* username: admin, password: 

* Run a Django manage command, first find the running django container
  >docker-compose ps
  >docker exec -it das_api bash


Non-Docker Development Environment Setup Steps
-----------------------------------------------------------------
* Clone the Github repo
* we suggest setting up a virtualenv for this project, activate it now
* on windows: populate a wheelhouse directory with some python 3.6 amd64 wheels
    * they are here: [dropbox](https://www.dropbox.com/sh/gtyw1jxlldw0h4z/AADLNMwr4ymtbEkqtrfabXuna?dl=0 "wheelhoue")
* install GEOS
    * on ubuntu: sudo apt-get install binutils libproj-dev gdal-bin libgeos-dev
    * on windows:
        * GEOS_LIBRARY_PATH = 'C:\projects\das\dasvir\Lib\site-packages\osgeo\geos_c.dll' in local_settings.py
        * add osgeo directory to env PATH, C:\projects\das\dasvir\Lib\site-packages\osgeo
* from a shell, cd to the project root

        pip install -r requirements.txt -r requirements-dev.txt -f <dir to wheelhouse - optional>
* mkdir \tmp, or change directory for MAPPING and LOGGING
* run the Django project which is made up of several parts:
    * Django API server
    
        python manage.py runserver 8000 --settings=das_server.local_settings
    * and/or - but watch the port numbers if running together
    * Realtime Socket IO server
    
        python manage.py rt_server 8000 --settings=das_server.local_settings
    * and
    * message queue listener - processes messages pushed in to pubsub
    
        python manage.py message_queue_listeners --settings=das_server.local_settings
 


Managing python requirements
---------------------------------------------------
We use pip-tools tools to manage our requirements so that project and all
dependent python packages are pinned to a specific version.

The canonical list of packages required for the project are contained in
dependencies/requirements.in
Pinned github commit references are kept in requirements-pinned.txt

run the following command to prepare a pinned set of dependencies for the app
* pip-compile requirements.in

run this command to update versions:
* pip-compile --upgrade

To install requirements using pip
* pip install -r requirements.txt -r requirements-pinned.txt --find-links <your wheelhouse dir>
