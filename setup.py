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

if sys.version_info <= (3, 4):
    error = 'ERROR: das requires Python Version 3.4 or above...exiting.'
    print(error, file=sys.stderr)
    sys.exit(1)

def readme():
    with open('readme.md') as f:
        return f.read()

setup(name = 'das',
      version = '0.1.1',
      description = 'Domain Awareness System, server',
      long_description = readme(),
      author = 'Vulcan',
      url = 'https://github.com/padas/das/',
      packages = ['das',],
      license = 'MIT',
      platforms = 'Posix; MacOS X; Windows',
      classifiers = ['Development Status :: 3 - Alpha',
                     'Intended Audience :: Developers',
                     'License :: OSI Approved :: BSD License',
                     'Operating System :: OS Independent',
                     'Topic :: Internet',
                     'Programming Language :: Python :: 3.4'],
      **extra
      )

