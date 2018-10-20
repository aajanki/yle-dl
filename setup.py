# -*- coding: utf-8 -*-

import re
import sys
from setuptools import setup

needs_pytest = set(['pytest', 'test', 'ptr']).intersection(sys.argv)
maybe_pytest_runner = ['pytest-runner'] if needs_pytest else []

long_description = \
u"""\
yle-dl is a tool for downloading media files from the video streaming
services of the Finnish national broadcasting company Yle: Yle
Areena, Elävä Arkisto and Yle news.

External dependencies: wget, ffmpeg. Certain streams also require:
rtmpdump, and a PHP interpreter with the following PHP extensions:
bcmath, curl, openssl and SimpleXML."""

version = re.\
  search(r"^version *= *'(.+)'$", open('yledl/version.py').read(), re.MULTILINE).\
  group(1)

# On older Pythons we need some additional libraries for SSL SNI support
ssl_sni_requires = []
if sys.version_info < (2, 7, 9):
    ssl_sni_requires = ['pyOpenSSL', 'ndg-httpsclient', 'pyasn1']

setup(
    name='yle-dl',
    version=version,
    description='Download videos from Yle servers',
    long_description=long_description,
    author='Antti Ajanki',
    author_email='antti.ajanki@iki.fi',
    url='https://aajanki.github.io/yle-dl/index-en.html',
    license='GNU GPLv3',
    packages=['yledl'],
    include_package_data=True,
    install_requires=[
        'pycryptodomex', 'requests', 'lxml', 'future', 'PySocks', 'mini-amf',
        'attrs >= 18.1.0, < 18.3.0', 'ConfigArgParse == 0.13.0'
    ] + ssl_sni_requires,
    extras_require = {
        'youtubedl-backend': ['youtube_dl']
    },
    setup_requires = maybe_pytest_runner,
    tests_require = [
        'pytest',
    ],
    entry_points = {
        'console_scripts': [
            'yle-dl = yledl.yledl:main'
        ]
    },
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Environment :: Console',
        'Intended Audience :: End Users/Desktop',
        'License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Topic :: Internet',
        'Topic :: Multimedia :: Video'
    ]
)
