#!/usr/bin/env python

from setuptools import setup, find_packages

setup(
    name='cotton',
    version='0.2.2',
    url='http://github.com/ministryofjustice/cotton',
    license='TBD',
    author='',
    author_email='',
    description='',
    long_description=__doc__,
    packages=find_packages(),
    namespace_packages=['cotton'],
    zip_safe=False,
    platforms='any',
    install_requires=[
        'fabric',
        'boto',
        'jinja2',
        'python-dateutil',
        'pyyaml',
        'GitPython>=0.3.2.RC1',
        'apache-libcloud>=0.14.0-beta3',
        'pptable',
        'lxml'
    ],
    classifiers=[
    ],
)
