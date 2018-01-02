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

Requires ffmpeg, rtmpdump, a PHP interpreter and the following PHP
extensions: bcmath, curl, mcrypt and SimpleXML."""

version = re.\
  search(r"^version *= *'(.+)'$", open('yledl/version.py').read(), re.MULTILINE).\
  group(1)

# On older Pythons we need some additional libraries for SSL SNI support
ssl_sni_requires = []
if sys.version_info < (2, 7, 9):
    ssl_sni_requires = ['pyOpenSSL', 'ndg-httpsclient', 'pyasn1']

if sys.version_info >= (3, 0, 0):
    pyamf_requires = ['Py3AMF']
else:
    pyamf_requires = ['PyAMF']

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
        'pycrypto', 'requests', 'lxml', 'future', 'PySocks'
    ] + pyamf_requires + ssl_sni_requires,
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
        'Topic :: Internet',
        'Topic :: Multimedia :: Video'
    ]
)
