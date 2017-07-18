# -*- coding: utf-8 -*-

import re
from setuptools import setup

long_description = \
u"""\
yle-dl is a tool for downloading media files from the video streaming
services of the Finnish national broadcasting company Yle: Yle
Areena, Elävä Arkisto and Yle news.

Requires ffmpeg, rtmpdump, a PHP interpreter and the following PHP
extensions: bcmath, curl, mcrypt and SimpleXML."""

version = re.\
  search(r"^version *= *'(.+)'$", open('yledl/yledl.py').read(), re.MULTILINE).\
  group(1)

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
        'pycrypto'
    ],
    extras_require = {
        'youtubedl-backend': ['youtube_dl']
    },
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
        'Topic :: Internet',
        'Topic :: Multimedia :: Video'
    ]
)
