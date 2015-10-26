download videos from Yle servers

Copyright (C) 2010-2015 Antti Ajanki, antti.ajanki@iki.fi

License: GPLv3

Homepage: http://aajanki.github.com/yle-dl/index-en.html

Source code: https://github.com/aajanki/yle-dl

yle-dl is a tool for downloading media files from the video streaming
services of the Finnish national broadcasting company Yle: [Yle
Areena], [Elävä Arkisto] and [Yle news].

[Yle Areena]:http://areena.yle.fi/
[Elävä arkisto]:http://yle.fi/aihe/elava-arkisto
[Yle news]:http://yle.fi/uutiset/

Installation
------------

Install dependencies: rtmpdump (version 2.4 or newer, preferably the
latest development version from the project homepage at
http://rtmpdump.mplayerhq.hu/), python (2.6 or newer) and pycrypto.
Either AdobeHDS.php or youtube-dl (the Python 2 module) is required to
download videos from Yle Areena. AdobeHDS.php additionally requires
php interpreter and the following php extensions: bcmath, curl, mcrypt
and SimpleXML.

On Debian the required packages can be installed either

* by `apt-get install rtmpdump python python-crypto php5-cli php5-curl php5-mcrypt`

* or by `apt-get install rtmpdump python python-crypto youtube-dl`

On OS X install rtmpdump with homebrew: `brew install --HEAD
rtmpdump` and pycrypto with pip: `pip install -r requirements.txt`

To install yle-dl run:

```
make install
```

Starting from version 1.99.9 yle-dl doesn't anymore require a modified
rtmpdump or plugin. Instead, everything is now downloadable with the
plain rtmpdump. To remove the remnants of previous versions run `make
uninstall-old-rtmpdump`.

Packages for various distros
----------------------------

[A list of available installation
packages](http://aajanki.github.com/yle-dl/index-en.html)

RPM packaging:

contrib/yle-dl.spec is a spec file for creating a RPM-package for
Fedora.

Usage
-----

```
yle-dl [options] URL
```

where URL is the address of the Areena or Elävä arkisto web page where
you would normally watch the video in a browser.

yle-dl options:

* `-o filename`       Save stream to the named file

* `--latestepisode`   Download the latest episodes

* `--showurl`         Print the URL of the stream, don't download

* `--showtitle`       Print stream title, don't download

* `--vfat`            Create Windows-compatible filenames

* `--sublang lang`    Download subtitles, lang = fin, swe, smi, none or all

* `--rtmpdump path`   Set path to rtmpdump binary

* `--adobehds cmd`    Set command for executing AdobeHDS.php script

* `--destdir dir`     Save files to dir

* `--pipe`            Dump stream to stdout for piping to media player. E.g. `yle-dl --pipe URL | vlc -`.

* `--protocol protos` Downloaders that are tried until one of them succeeds (a comma-separated list). Possible values: `hds` (download a stream using AdobeHDS.php), `hds:youtubedl` (youtube-dl), and `rtmp` (rtmpdump).

* `-V, --verbose`     Show verbose debug output

Type `yle-dl --help` to see the full list of options.

Any unrecognized options will be relayed to rtmpdump process (when
downloading RTMP streams).

Firewall must allow outgoing traffic on ports 80 and 1935.

Examples
--------

```
yle-dl http://areena.yle.fi/1-1544491 -o video.flv
```

```
yle-dl --protocol hds:youtubedl http://areena.yle.fi/1-1544491 -o video.flv
```

```
yle-dl http://yle.fi/aihe/artikkeli/2010/10/28/studio-julmahuvi-roudasta-rospuuttoon
```

Playing in mplayer (or vlc and others) without downloading first:

```
yle-dl --pipe http://areena.yle.fi/1-2409251 | mplayer -cache 1024 -
```
