Project DAS - Domain Awareness System
=================================================================


Developer Setup
=================================================================
Requirements
-----------------------------------------------------------------

* Python 3.4 (pip and virtualenv)
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

Steps
-----------------------------------------------------------------
* Clone the Github repo
* we suggest setting up a virtualenv for this project, activate it now
* on windows: populate a wheelhouse directory with some python 3.4 amd64 wheels
    * they are here: [dropbox](https://www.dropbox.com/sh/gtyw1jxlldw0h4z/AADLNMwr4ymtbEkqtrfabXuna?dl=0 "wheelhoue")
* install GEOS
    * on ubuntu: sudo apt-get install binutils libproj-dev gdal-bin libgeos-dev
    * on windows:
        * GEOS_LIBRARY_PATH = 'C:\projects\das\dasvir\Lib\site-packages\osgeo\geos_c.dll' in local_settings.py
        * add osgeo directory to env PATH, C:\projects\das\dasvir\Lib\site-packages\osgeo
* from a shell, cd to the project root

        pip install -r requirements.txt -f <dir to wheelhouse - optional>
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
    



for dev, install additional requirements
--------------------------------------------------
    pip install -r requirement-dev.txt -f wheelhouse

