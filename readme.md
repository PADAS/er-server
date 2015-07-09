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
We use Pep8 of course
4 space indents
'' single quotes around strings as much as possible



Steps
-----------------------------------------------------------------
* Clone the Github repo
* suggest setting up a virtualenv for this project, activate it now
* from a shell, cd to the project root
* pip install -r requirements.txt --find-links wheelhouse
* install GEOS
  * on ubuntu: sudo apt-get install binutils libproj-dev gdal-bin libgeos-dev
  * on windows: install Shapely wheel "pip install Shapely==1.5.9 --find-links wheelhouse"
   then set as appropriate GEOS_LIBRARY_PATH = 'C:\python34\Lib\site-packages\shapely\DLLs\geos_c.dll' in local_settings.py
   
* run the Django project
* python manage.py runserver 8080



for dev, install additional requirements
* pip install -r requirement-dev.txt --find-links wheelhouse

