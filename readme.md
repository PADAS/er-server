Project DAS - Domain Awareness System
=================================================================


Developer Setup
=================================================================
Requirements
-----------------------------------------------------------------

* Python 3.4 (pip and virtualenv)
* Postgres 9.4

Coding Conventions
-----------------------------------------------------------------
We use PEP8 of course
4 space indents
'' single quotes around strings as much as possible



Steps
-----------------------------------------------------------------
* Clone the Github repo
* we suggest setting up a virtualenv for this project, activate it now
* on windows: populate the wheelhouse directory with some python 3.4 amd64 wheels
    * they are here: [dropbox](https://www.dropbox.com/sh/gtyw1jxlldw0h4z/AADLNMwr4ymtbEkqtrfabXuna?dl=0 "wheelhoue")
* install GEOS
    * on ubuntu: sudo apt-get install binutils libproj-dev gdal-bin libgeos-dev
    * on windows: GEOS_LIBRARY_PATH = 'C:\python34\Lib\site-packages\shapely\DLLs\geos_c.dll' in local_settings.py
* from a shell, cd to the project root
* pip install -r requirements.txt -f wheelhouse
* run the Django project
    * python manage.py runserver 8080


for dev, install additional requirements
* pip install -r requirement-dev.txt -f wheelhouse

