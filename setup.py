#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Setup script for the DAS server
"""
import sys

try:
    from setuptools import setup
    extra = {}
except ImportError:
    from distutils.core import setup
    extra = {}

if sys.version_info <= (3, 6):
    error = 'ERROR: das requires Python Version 3.6 or above...exiting.'
    print(error, file=sys.stderr)
    sys.exit(1)


from das.das_server import VERSION, __version__

branch = VERSION[3]
if not branch:
    STATUS = ['Development Status :: 5 - Production/Stable']
elif 'dev' in branch:
    STATUS = ['Development Status :: 4 - Develop']
elif 'rc' in branch:
    STATUS = ['Development Status :: 4 - Release Candidate']
elif 'sup' in branch:
    STATUS = ['Development Status :: 4 - Support']
else:
    STATUS = ['Development Status :: 3 - Unknown']


def readme():
    with open('readme.md') as f:
        return f.read()

setup(name='das',
      version=__version__,
      description='Domain Awareness System, server',
      long_description=readme(),
      author='Vulcan',
      url='https://github.com/padas/das/',
      packages=('das',),
      license='MIT',
      platforms='Posix; MacOS X; Windows',
      classifiers=STATUS + [
          'Framework :: Django',
          'Intended Audience :: Developers',
          'License :: OSI Approved :: BSD License',
          'Operating System :: OS Independent',
          'Topic :: Internet',
          'Programming Language :: Python :: 3.6'
          ],
      **extra
      )

