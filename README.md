Download videos from Yle servers

[![Build Status](https://travis-ci.org/aajanki/yle-dl.svg?branch=master)](https://travis-ci.org/aajanki/yle-dl)
[![PyPI version](https://badge.fury.io/py/yle-dl.svg)](https://badge.fury.io/py/yle-dl)

Copyright (C) 2010-2020 Antti Ajanki, antti.ajanki@iki.fi

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
instructions for Debian, Ubuntu, Mac OS X, Windows and Android.

### 1. Install the dependencies ###

* Python 2.7 or 3.5+
* pip
* pycryptodome
* ffmpeg (subtitles fully supported only on ffmpeg 4.1 or later)
* setuptools (when installing from the sources)

Optionally for few rare streams:

* PHP interpreter with bcmath, curl, openssl and SimpleXML extensions: some news broadcasts
* rtmpdump: some Elävä Arkisto streams. Version 2.4 or newer, preferably the latest development version from the [project homepage](https://rtmpdump.mplayerhq.hu/)
* wget

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

### 3. Fix the search path if necessary ###

If the command line shell complains that it can't find yle-dl when you try to execute it, add the installation location onto your $PATH:
```
# Set the path for the current terminal session
export PATH=$PATH:$HOME/.local/bin

# Make the change permanent. Adjust as needed if you are not using bash
echo export PATH=$PATH:\$HOME/.local/bin >> ~/.bashrc
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
Areena streams are available only in Finland. By default these tests
are skipped. The run all tests, set the environment variable
`ENABLE_FINLAND_TESTS` to 1:

```
export ENABLE_FINLAND_TESTS=1
python3 setup.py pytest
```

Running only a single test file:

```
python3 setup.py pytest --addopts "-k tests/integration/test_areena_radio_it.py"
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

* `--postprocess cmd` Execute a command cmd after a successful download. The command is called with the downloaded video file as the first parameter and subtitle files (if any) as the following parameters.

* `--proxy uri`       HTTP(S) proxy to use. Example: `--proxy localhost:8118`

* `--destdir dir`     Save files to dir

* `--pipe`            Dump stream to stdout for piping to media player. E.g. `yle-dl --pipe URL | vlc -`.

* `--backend vals`    Downloaders that are tried until one of them succeeds (a comma-separated list). Possible values: `adobehdsphp` (download HDS streams using AdobeHDS.php), `youtubedl` (download HDS streams using youtube-dl).

* `-V, --verbose`     Show verbose debug output

Type `yle-dl --help` to see the full list of options.

Any unrecognized options will be relayed to rtmpdump process (when
downloading RTMP streams).

To download through a SOCKS5 proxy, use [tsocks](http://tsocks.sourceforge.net/) or a similar wrapper.

Firewall must allow outgoing traffic on ports 80 and 1935.


Addresses for live TV broadcasts
--------------------------------

```
yle-dl https://areena.yle.fi/tv/suorat/yle-tv1

yle-dl https://areena.yle.fi/tv/suorat/yle-tv2

yle-dl https://areena.yle.fi/tv/suorat/yle-teema-fem
```


Config file
-----------

Arguments that start with '--' can also be set in a config file. The
default config file is `~/.yledl.conf` or one can be specified via
`--config`. See [yledl.conf.sample](yledl.conf.sample) for an example
configuration.

Config file syntax allows: key=value, flag=true. If an arg is
specified in more than one place, then command line values override
config file values which override defaults.


Examples
--------

```
yle-dl https://areena.yle.fi/1-1544491 -o video.mkv
```

```
yle-dl --backend youtubedl https://areena.yle.fi/1-1544491 -o video.mkv
```

```
yle-dl http://yle.fi/aihe/artikkeli/2010/10/28/studio-julmahuvi-roudasta-rospuuttoon
```

Playing in vlc (or any other video player) without downloading first:

```
yle-dl --pipe https://areena.yle.fi/1-2409251 | mpv --cache=1000 --slang=fi -
```

Executing a script to postprocess a downloaded video (see the example postprocessing script at scripts/muxmp4):

```
yle-dl --postprocess scripts/muxmp4 https://areena.yle.fi/1-1864726
```
