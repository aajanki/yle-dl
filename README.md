Download videos from Yle servers

[![Build status](https://circleci.com/gh/aajanki/yle-dl.svg?style=shield)](https://app.circleci.com/pipelines/github/aajanki/yle-dl)
[![PyPI version](https://badge.fury.io/py/yle-dl.svg)](https://badge.fury.io/py/yle-dl)

Copyright (C) 2010-2024 Antti Ajanki, antti.ajanki@iki.fi

License: GPL v3 or later

Homepage: https://aajanki.github.io/yle-dl/index-en.html

Source code: https://github.com/aajanki/yle-dl

yle-dl is a tool for downloading media files from the video streaming
services of the Finnish national broadcasting company Yle: [Yle
Areena], [Elävä Arkisto] and [Yle news].

[Yle Areena]:https://areena.yle.fi/
[Elävä arkisto]:https://yle.fi/aihe/elava-arkisto
[Yle news]:https://yle.fi/

Installation
------------

Below are general installation instructions. See a [separate
page](OS-install-instructions.md) for specialized installation
instructions for Debian, Ubuntu, Mac OS X, Windows and Android.

### 1. Install the dependencies ###

* Python 3.8+
* ffmpeg (subtitles fully supported only on ffmpeg 4.1 or later)
* wget (required for podcasts)

### 2. Install yle-dl ###

1. [Install pipx](https://pypa.github.io/pipx/)
2. Install yle-dl: `pipx install yle-dl`

Installing yle-dl with all optional dependencies (`pipx install yle-dl[extra]`)
enables storing video metadata as extended file attributes and automatically
detecting filesystems that require restricted character sets.

Alternatively, installing the source distribution in the editable mode: Download the sources
and run the following in the source directory: `pip3 install --user .`

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

### Using with libav instead of ffmpeg

```
yle-dl --ffmpeg avconv --ffprobe avprobe ...
```

Config file
-----------

Arguments that start with '--' can also be set in a config file. The default
config file is `~/.yledl.conf` (or alternatively `~/.config/yledl.conf`) or
one can be specified via `--config`. See [yledl.conf.sample](yledl.conf.sample)
for an example configuration.

Config file syntax allows: key=value, flag=true. If an arg is
specified in more than one place, then command line values override
config file values which override defaults.

Contributed packages for various distros
----------------------------------------

[A list of contributed packages](https://aajanki.github.io/yle-dl/index-en.html#packages)

Examples
--------

### Yle Areena

Save an Areena stream to a file with an automatically generated name:
```
yle-dl https://areena.yle.fi/1-787136
```

Save a stream to a file called video.mkv:
```
yle-dl https://areena.yle.fi/1-787136 -o video.mkv
```

Playing in mpv (or in vlc or in any other video player) without downloading first:

```
yle-dl --pipe https://areena.yle.fi/1-787136 | mpv --slang=fi -
```

Executing a script to postprocess a downloaded video (see the example postprocessing script at scripts/muxmp4):

```
yle-dl --postprocess scripts/muxmp4 https://areena.yle.fi/1-787136
```

### Areena live TV broadcasts

```
yle-dl tv1

yle-dl tv2

yle-dl teema
```

Record the broadcast shown an hour (3600 seconds) ago:

```
yle-dl --startposition -3600 tv1
```

### Elävä Arkisto

```
yle-dl https://yle.fi/aihe/artikkeli/2010/10/28/studio-julmahuvi-roudasta-rospuuttoon
```

### Embedded videos on the yle.fi news articles

```
yle-dl https://yle.fi/a/74-20036911
```

Development
-----------

Install yle-dl in editable mode:

```
pip install --break-system-packages --user -e .[test,extra]
```

Install the pre-commit hooks for linting and type checking:

```
pipx install pre-commit

pre-commit install
```

### Unit and integration tests

```
pytest-3
```

Some tests succeed only when run on a Finnish IP address because some
Areena streams are available only in Finland. By default, these tests
are skipped. To run all tests, include the "--geoblocked" flag:

```
pytest-3 --geoblocked
```

Running only a single test file:

```
pytest-3 tests/integration/test_areena_radio_it.py
```

Creating a new release
----------------------

[Release instructions](releasing.md)

Bug reports and feature suggestions
-----------------------------------

If you encounter a bug or have an idea for a new feature, please post
it to [Github issue
tracker](https://github.com/aajanki/yle-dl/issues). You can write in
English or in Finnish.

Known problems
--------------

#### Problem: Subtitles are visible only for the first five minutes.

Solution: Update your ffmpeg to version 4.1 or later.

#### Problem: Subtitles are missing on live stream

This is a known problem. Currently, there are no fixes.

#### Problem: I get warnings about unsupported subtitles and dropping subtitles

Downloading always produces certain warnings messages that are harmless and can
be ignored. Subtitles should get downloaded correctly in most cases despite the warnings.

At least messages similar to the following are safe to ignore:
- mime type is not rfc8216 compliant
- Can't support the subtitle(uri: ...)
- Dropping 114 duplicated subtitle events
- Unsupported codec with id 98313 for input stream 5

#### Problem: I installed yle-dl but get an error message "command not found" when I try to run it

The installation location is not on shell's search path. Use the full path to run yle-dl: `~/.local/bin/yle-dl`

Better yet, append the search path permanently by editing shell's config file. For example, on bash do the following:

```
echo "export PATH=\"\$HOME/.local/bin:\$PATH\"" >> ~/.bashrc && source ~/.bashrc
```
