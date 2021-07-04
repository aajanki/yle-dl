Download videos from Yle servers

[![Build status](https://circleci.com/gh/aajanki/yle-dl.svg?style=shield)](https://app.circleci.com/pipelines/github/aajanki/yle-dl)
[![PyPI version](https://badge.fury.io/py/yle-dl.svg)](https://badge.fury.io/py/yle-dl)

Copyright (C) 2010-2021 Antti Ajanki, antti.ajanki@iki.fi

License: GPLv3

Homepage: https://aajanki.github.io/yle-dl/index-en.html

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

* Python 3.6+
* pip
* ffmpeg (subtitles fully supported only on ffmpeg 4.1 or later)
* setuptools (when installing from the sources)

Optionally for few rare streams:

* wget

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

* `--sublang lang`    Disable subtitles if lang is "none"

* `--resolution res`  Maximum vertical resolution in pixels

* `--maxbitrate br`   Maximum bitrate stream to download, integer in kB/s or "best" or "worst". Not all streams support limited bitrates.

* `--postprocess cmd` Execute a command cmd after a successful download. The command is called with the downloaded video file as the first parameter and subtitle files (if any) as the following parameters.

* `--proxy uri`       HTTP(S) proxy to use. Example: `--proxy localhost:8118`

* `--destdir dir`     Save files to dir

* `--pipe`            Dump stream to stdout for piping to media player. E.g. `yle-dl --pipe URL | vlc -`.

* `-V, --verbose`     Show verbose debug output

Type `yle-dl --help` to see the full list of options.

To download through a SOCKS5 proxy, use [tsocks](http://tsocks.sourceforge.net/) or a similar wrapper.

### Addresses for live TV broadcasts

```
yle-dl https://areena.yle.fi/tv/suorat/yle-tv1

yle-dl https://areena.yle.fi/tv/suorat/yle-tv2

yle-dl https://areena.yle.fi/tv/suorat/yle-teema-fem
```

Record the broadcast shown an hour (3600 seconds) ago:

```
yle-dl --startposition -3600 https://areena.yle.fi/tv/suorat/yle-tv1
```

### Using with libav instead of ffmpeg

```
yle-dl --ffmpeg avconv --ffprobe avprobe ...
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

Contributed packages for various distros
----------------------------------------

[A list of contributed packages](https://aajanki.github.io/yle-dl/index-en.html#packages)

Integration tests
-----------------

```
pytest-3
```

Some tests succeed only when run on a Finnish IP address because some
Areena streams are available only in Finland. By default these tests
are skipped. To run all tests, include the "--geoblocked" flag:

```
pytest-3 --geoblocked
```

Running only a single test file:

```
pytest-3 tests/integration/test_areena_radio_it.py
```

Examples
--------

```
yle-dl https://areena.yle.fi/1-1544491 -o video.mkv
```

```
yle-dl http://yle.fi/aihe/artikkeli/2010/10/28/studio-julmahuvi-roudasta-rospuuttoon
```

Playing in mpv (or in vlc or in any other video player) without downloading first:

```
yle-dl --pipe https://areena.yle.fi/1-2409251 | mpv --cache=1000 --slang=fi -
```

Executing a script to postprocess a downloaded video (see the example postprocessing script at scripts/muxmp4):

```
yle-dl --postprocess scripts/muxmp4 https://areena.yle.fi/1-1864726
```

Known problems
--------------

#### Problem: Subtitles are visible only for the first five minutes.

Solution: Update your ffmpeg to version 4.1 or later.

#### Problem: Trying to fetch a radio series only downloads the first episode on Mac OS X.

This is an [open issue](https://github.com/aajanki/yle-dl/issues/261).
The workaround is to download each episode one by one.

#### Problem: I installed yle-dl but get an error message "command not found" when I try to run it

The installation location is not on shell's search path. Use the full path to run yle-dl: `~/.local/bin/yle-dl`

Better yet, append the search path permanently by editing shell's config file. For example, on bash do the following:

```
echo "export PATH=\"\$HOME/.local/bin:\$PATH\"" >> ~/.bashrc && source ~/.bashrc
```
