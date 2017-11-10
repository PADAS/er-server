#!/usr/bin/env python
import os
import sys

#
# This alternate version of manage.py will allow you to run a command in a mode that allows you to connect to it
# using Visual Studio Code remote debugger.
#
# By default, it listens for debugger attachment on port 5400. This requires the container to expose the port.
# If you look at compose-dev.yml and see the ports for the API container, then you'll see how to make this available
# on port 5400 of your localhost.
#

try:
    import ptvsd
except ImportError:
    ptvsd = None

if os.environ.get('EVENTLET_SHOULDPATCH', 'false').lower() == 'true':
    import eventlet
    if os.environ.get('EVENTLET_ATTACH_DEBUG', 'false').lower() == 'true':
        eventlet.monkey_patch(all=False, socket=True,
                              select=True, thread=False)
    else:
        eventlet.monkey_patch()

from das_server.log import init_logging
init_logging()

"""
To run the local server:
python manage.py runserver 8080
OR
python manage.py runserver 8080 --settings=das_server.local_settings

"""

if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "das_server.settings")

    from django.core.management import execute_from_command_line

    if ptvsd and 'runserver' in sys.argv and os.environ.get('ENABLE_DEBUG', 'False') == 'True':
        try:
            print('enabling debug attach.')
            ptvsd.enable_attach('goodforme', address=('0.0.0.0', 5400))
        except Exception as e:
            print('Failed to enable debug attach. ex=%s' % (e,))

    os.environ.setdefault('ENABLE_DEBUG', 'True')
    execute_from_command_line(sys.argv)
