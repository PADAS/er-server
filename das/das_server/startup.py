import os
from django.conf import settings
from importlib import import_module
from django.utils.module_loading import module_has_submodule
import re

def autoload(submodules, ignorelist=(), ignore_re='(djgeojson|django)'):
    '''
    Automatically import {{ app_name }}.startup modules.
    :param submodules: module name(s) within INSTALLED_APPS.
    :param ignorelist: a list of apps to ignore.
    :param ignore_re: an re to ignore via match.
    :return:
    '''
    for app in settings.INSTALLED_APPS:
        mod = import_module(app)
        for submodule in submodules:

            if re.match(ignore_re, app) or app in ignorelist:
                continue

            try:
                mn = "{}.{}".format(app, submodule)
                import_module(mn)
                print('Imported startup module %s' % (mn,))
            except:
                if module_has_submodule(mod, submodule):
                    raise


def run():
    '''
    For now we automatically import startup submodules, namely das_input.startup which initializes a
    scheduler and some data import jobs.
    :return:
    '''
    autoload(["startup"])

if __name__ == '__main__':
    run()
    input("Press Enter to exit")
