# -*- coding: utf-8 -*-

from setuptools import setup

long_description = \
u"""\
yle-dl is a tool for downloading media files from the video streaming
services of the Finnish national broadcasting company Yle: Yle
Areena, Elävä Arkisto and Yle news.

Requires a PHP interpreter and the following PHP extensions: bcmath,
curl, mcrypt and SimpleXML.
"""

setup(name='yle-dl',
      version='2.10.0',
      description='Download videos from Yle servers',
      long_description=long_description,
      author='Antti Ajanki',
      author_email='antti.ajanki@iki.fi',
      url='https://aajanki.github.io/yle-dl/index-en.html',
      license='GNU GPLv3',
      scripts=['yle-dl'],
      data_files=[('/usr/local/share/yle-dl', ['AdobeHDS.php'])],
      install_requires=[
          'pycrypto'
      ],
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
