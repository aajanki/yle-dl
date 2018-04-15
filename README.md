Download videos from Yle servers

[![Build Status](https://travis-ci.org/aajanki/yle-dl.svg?branch=master)](https://travis-ci.org/aajanki/yle-dl)
[![PyPI version](https://badge.fury.io/py/yle-dl.svg)](https://badge.fury.io/py/yle-dl)

Copyright (C) 2010-2018 Antti Ajanki, antti.ajanki@iki.fi

License: GPLv3

Homepage: https://aajanki.github.com/yle-dl/index-en.html

Source code: https://github.com/aajanki/yle-dl

yle-dl is a tool for downloading media files from the video streaming
services of the Finnish national broadcasting company Yle: [Yle
Areena], [Elävä Arkisto] and [Yle news].

[Yle Areena]:https://areena.yle.fi/
[Elävä arkisto]:http://yle.fi/aihe/elava-arkisto
[Yle news]:http://yle.fi/uutiset/

Installation
------------

Below are general installation instructions. See a [separate
page](OS-install-instructions.md) for specialized installation
instructions for Debian, Ubuntu, Mac OS X and Windows.

### 1. Install the dependencies ###

* Python 2.7 or 3.5+
* pip
* pycryptodome
* wget
* ffmpeg
* setuptools (when installing from the sources)

Optionally for certain types of streams:

* PHP interpreter with bcmath, curl, openssl and SimpleXML extensions: live TV and certain news broadcasts
* rtmpdump: Areena audio streams. Version 2.4 or newer, preferably the latest development version from the [project homepage](https://rtmpdump.mplayerhq.hu/)

Enable the PHP extensions by appending the following lines with the
correct paths in the [php.ini]:

[php.ini]:https://secure.php.net/manual/en/configuration.file.php

```
extension=/path/to/curl.so
```

### 2. Install yle-dl ###

Easier way (installation without downloading the source codes):
```
pip3 install --user --upgrade yle-dl
```

Installation from sources. Download the sources and run the following
on the source directory:
```
python3 setup.py install --user
```

Installation with youtube-dl as an alternative downloader backend
-----------------------------------------------------------------

By default, yle-dl downloads streams from Yle Areena using the
included copy of AdobeHDS.php. If the default downloader does not work
for some reason, it is possible to use youtube-dl instead. yle-dl will
automatically fall back to youtube-dl if it is installed and
downloading with AdobeHDS.php fails.

Follow the above installation instructions (except for the PHP and the
PHP libraries) and additionally install youtube-dl:

* Mac OS X: `brew install youtube-dl`
* Debian/Ubuntu/other operating systems: `pip3 install --user --upgrade youtube_dl`

Using with libav instead of ffmpeg
----------------------------------

```
yle-dl --ffmpeg avconv --ffprobe avprobe ...
```

Integration tests
-----------------

```
python3 setup.py pytest
```

Some tests succeed only when run on a Finnish IP address because some
Areena streams are available only in Finland. To skip those test, set
the environment variable `ENABLE_FINLAND_TESTS` to 0:

```
export ENABLE_FINLAND_TESTS=0
python3 setup.py pytest
```

Packages for various distros
----------------------------

[A list of available
packages](https://aajanki.github.com/yle-dl/index-en.html)


Usage
-----

```
yle-dl [options] URL
```

or

```
yle-dl [options] -i filename
```

where URL is the address of the Areena or Elävä arkisto web page where
you would normally watch the video in a browser.

yle-dl options:

* `-o filename`       Save stream to the named file

* `-i filename`       Read input URLs to process from the named file, one URL per line

* `--latestepisode`   Download the latest episodes

* `--showurl`         Print the URL of the stream, don't download

* `--showtitle`       Print stream title, don't download

* `--showmetadata`    Print stream [metadata as JSON](docs/metadata.md)

* `--vfat`            Create Windows-compatible filenames

* `--audiolang lang`  Select stream's audio language if available, lang = fin (default) or swe

* `--sublang lang`    Download stream's subtitle language, lang = fin, swe, smi, none or all (default)

* `--resolution res`  Maximum vertical resolution in pixels

* `--maxbitrate br`   Maximum bitrate stream to download, integer in kB/s or "best" or "worst". Not all streams support limited bitrates.

* `--rtmpdump path`   Set path to rtmpdump binary

* `--adobehds cmd`    Set command for executing AdobeHDS.php script

* `--postprocess cmd` Execute a command cmd after a successful download. The command is called with the downloaded FLV file as the first parameter and subtitle files (if any) as the following parameters.

* `--proxy uri`       Proxy for downloading stream manifests. Example: `--proxy socks5://localhost:7777`

* `--destdir dir`     Save files to dir

* `--pipe`            Dump stream to stdout for piping to media player. E.g. `yle-dl --pipe URL | vlc -`.

* `--backend vals`    Downloaders that are tried until one of them succeeds (a comma-separated list). Possible values: `adobehdsphp` (download HDS streams using AdobeHDS.php), `youtubedl` (download HDS streams using youtube-dl).

* `-V, --verbose`     Show verbose debug output

Type `yle-dl --help` to see the full list of options.

Any unrecognized options will be relayed to rtmpdump process (when
downloading RTMP streams).

Firewall must allow outgoing traffic on ports 80 and 1935.

Examples
--------

```
yle-dl https://areena.yle.fi/1-1544491 -o video.flv
```

```
yle-dl --backend youtubedl https://areena.yle.fi/1-1544491 -o video.flv
```

```
yle-dl http://yle.fi/aihe/artikkeli/2010/10/28/studio-julmahuvi-roudasta-rospuuttoon
```

Playing in vlc (or any other video player) without downloading first:

```
yle-dl --pipe https://areena.yle.fi/1-2409251 | vlc --file-caching=10000 --sub-track=0 -
```

Executing a script to postprocess a downloaded video (see the example postprocessing script at scripts/muxmp4):

```
yle-dl --postprocess scripts/muxmp4 https://areena.yle.fi/1-1864726
```

Set default values for arguments using `alias`:

```
alias yle-dl-defaults="yle-dl --resolution 720p --destdir ~/videos"
yle-dl-defaults https://areena.yle.fi/1-1864726
```
