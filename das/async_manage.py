#!/usr/bin/env python
import os
import sys

import eventlet
eventlet.monkey_patch()

from das_server.log import init_logging
init_logging()

"""
To run the local server:
python async_manage.py runserver 8080
OR
python async_manage.py runserver 8080 --settings=das_server.local_settings

"""

if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "das_server.settings")

    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)
