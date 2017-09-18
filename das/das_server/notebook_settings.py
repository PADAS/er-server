from das_server.local_settings_docker import *

INSTALLED_APPS += ('django_extensions',
                   )

NOTEBOOK_ARGUMENTS = [
    '--ip', '0.0.0.0',
    '--port', '8888',
    '--allow-root',
    '--no-browser',
]
