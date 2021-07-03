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

External dependencies: ffmpeg and wget."""

version = re.\
  search(r"^version *= *'(.+)'$", open('yledl/version.py').read(), re.MULTILINE).\
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
        'requests', 'lxml',
        'attrs >= 18.1.0', 'ConfigArgParse >= 0.13.0'
    ],
    setup_requires = maybe_pytest_runner,
    tests_require = [
        'pytest',
    ],
    entry_points = {
        'console_scripts': [
            'yle-dl = yledl.yledl:main'
        ]
    },
    python_requires='>=3.6',
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Environment :: Console',
        'Intended Audience :: End Users/Desktop',
        'License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Topic :: Internet',
        'Topic :: Multimedia :: Video'
    ]
)
