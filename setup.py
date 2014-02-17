#!/usr/bin/env python

from setuptools import setup

setup(
    name='cotton',
    version='0.1.1-alpha',
    url='http://github.com/ministryofjustice/cotton',
    license='TBD',
    author='',
    author_email='',
    description='',
    long_description=__doc__,
    packages=['cotton'],
    namespace_packages=['cotton'],
    zip_safe=False,
    platforms='any',
    install_requires=[
        'fabric',
        'boto',
        'ipython',
        'jinja2',
        'python-dateutil',
    ],
    classifiers=[
    ],
)
