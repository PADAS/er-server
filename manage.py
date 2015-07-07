#!/usr/bin/env python
import os
import sys


"""
To run the local server:
python manage.py runserver 8080
OR
python manage.py runserver 8080 --settings=das.local_settings

"""

if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "das.settings")

    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)
