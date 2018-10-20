#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
yle-dl - download videos from Yle servers

Copyright (C) 2010-2018 Antti Ajanki <antti.ajanki@iki.fi>

This script downloads video and audio streams from Yle Areena
(https://areena.yle.fi) and Elävä Arkisto
(http://yle.fi/aihe/elava-arkisto).
"""

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import print_function, absolute_import, unicode_literals
import sys
import re
import codecs
import logging
import configargparse
from future.moves.urllib.parse import urlparse, urlunparse, quote
from .backends import Backends
from .downloader import YleDlDownloader, SubtitleDownloader
from .exitcodes import RD_SUCCESS, RD_FAILED
from .extractors import extractor_factory
from .http import HttpClient
from .io import IOContext, DownloadLimits
from .streamfilters import StreamFilters
from .utils import print_enc
from .version import version


def yledl_logger():
    class PlainInfoFormatter(logging.Formatter):
        def format(self, record):
            if record.levelno == logging.INFO:
                return record.getMessage()
            else:
                return super(PlainInfoFormatter, self).format(record)

    logger = logging.getLogger('yledl')
    handler = logging.StreamHandler()
    formatter = PlainInfoFormatter('%(levelname)s: %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger


logger = yledl_logger()


class StreamAction(object):
    DOWNLOAD = 1
    PIPE = 2
    PRINT_STREAM_URL = 3
    PRINT_STREAM_TITLE = 4
    PRINT_EPISODE_PAGES = 5
    PRINT_METADATA = 6
    DOWNLOAD_SUBTITLES_ONLY = 7


def arg_parser():
    class ArgumentParserEncoded(configargparse.ArgumentParser):
        def _print_message(self, message, file=None):
            if message:
                if file is None:
                    file = sys.stderr
                print_enc(message, file, False)

    def to_unicode(s):
        enc = sys.getfilesystemencoding()
        try:
            # Python 2
            if type(s) == unicode:
                # default values are unicode even on Python 2
                return s
            else:
                return unicode(s, enc)
        except NameError:
            # Python 3
            return s

    description = \
        ('yle-dl %s: Download media files from Yle Areena and Elävä Arkisto\n'
         'Copyright (C) 2009-2018 Antti Ajanki <antti.ajanki@iki.fi>, '
         'license: GPLv3\n' % version)

    parser = ArgumentParserEncoded(
        default_config_files=['~/.yledl.conf'],
        description=description,
        formatter_class=configargparse.RawDescriptionHelpFormatter)
    parser.add_argument('-V', '--verbose', '--debug',
                        action='store_true', dest='debug',
                        help='Show verbose debug output')
    parser.add_argument('-c', '--config', metavar='FILENAME',
                        is_config_file=True, help='config file path')

    io_group = parser.add_argument_group('Input and output')
    url_group = io_group.add_mutually_exclusive_group()
    url_group.add_argument('url', nargs='?', type=to_unicode,
        help='Address of an Areena, Elävä Arkisto, or Yle news web page')
    url_group.add_argument('-i', metavar='FILENAME', dest='inputfile',
                           type=to_unicode,
                           help='Read input URLs to process from the named '
                           'file, one URL per line')
    io_group.add_argument('-o', metavar='FILENAME', dest='outputfile',
                          type=to_unicode,
                          help='Save stream to the named file')
    io_group.add_argument('--pipe', action='store_true',
                          help='Dump stream to stdout for piping to media '
                          'player. E.g. "yle-dl --pipe URL | vlc -"')
    io_group.add_argument('--destdir', metavar='DIR',
                          type=to_unicode,
                          help='Save files to DIR')
    action_group = io_group.add_mutually_exclusive_group()
    action_group.add_argument('--showurl', action='store_true',
                              help="Print URL, don't download")
    action_group.add_argument('--showtitle', action='store_true',
                              help="Print stream title, don't download")
    action_group.add_argument('--showepisodepage', action='store_true',
                              help='Print web page for each episode')
    action_group.add_argument('--showmetadata', action='store_true',
                              help='Print metadata about available streams')
    action_group.add_argument('--subtitlesonly', action='store_true',
                              help='Download only subtitles, not the video')
    io_group.add_argument('--vfat', action='store_true',
                          help='Output Windows-compatible filenames')
    io_group.add_argument('--resume', action='store_true',
                          help='Resume a partial download')
    io_group.add_argument('--ratelimit', metavar='BR', type=int,
                          help='Maximum bandwidth consumption, '
                          'interger in kB/s')
    io_group.add_argument('--proxy', metavar='URI',
                          type=to_unicode,
                          help='HTTP(S) proxy to use. Example: --proxy localhost:8118')
    io_group.add_argument('--postprocess', metavar='CMD',
                          type=to_unicode,
                          help='Execute the command CMD after a successful '
                          'download. CMD is called with two arguments: '
                          'video, subtitle')

    qual_group = parser.add_argument_group('Stream type and quality')
    qual_group.add_argument('--audiolang', metavar='LANG',
                            type=to_unicode,
                            choices=['fin', 'swe'], default='',
                            help='Select stream\'s audio language, "fin" or '
                            '"swe"')
    qual_group.add_argument('--sublang', metavar='LANG',
                            type=to_unicode,
                            choices=['fin', 'swe', 'smi', 'none', 'all'],
                            help='Download subtitles. LANG is one of "fin", '
                            '"swe", "smi", "none", or "all"')
    qual_group.add_argument('--hardsubs', action='store_true',
                            help='Download stream with hard subs if available')
    qual_group.add_argument('--latestepisode', action='store_true',
                            help='Download the latest episode of a series')
    qual_group.add_argument('--maxbitrate', metavar='RATE',
                            type=to_unicode,
                            help='Maximum bitrate stream to download, '
                            'integer in kB/s or "best" or "worst".')
    qual_group.add_argument('--resolution', metavar='RES',
                            type=to_unicode,
                            help='Maximum vertical resolution in pixels, '
                            'default: highest available resolution')
    qual_group.add_argument('--duration', metavar='S', type=int,
                            help='Record only the first S seconds of '
                            'the stream')

    dl_group = parser.add_argument_group('Downloader backends')
    dl_group.add_argument('--backend', metavar='BE',
                          type=to_unicode,
                          default="wget,ffmpeg,adobehdsphp,youtubedl,rtmpdump",
                          help='Downloaders that are tried until one of them '
                          ' succeeds (a comma-separated list). '
                          'Possible values: '
                          '"wget", '
                          '"ffmpeg", '
                          '"adobehdsphp" = AdobeHDS.php, '
                          '"youtubedl" = youtube-dl, '
                          '"rtmpdump"')
    dl_group.add_argument('--rtmpdump', metavar='PATH',
                          type=to_unicode,
                          help='Set path to the rtmpdump binary')
    dl_group.add_argument('--ffmpeg', metavar='PATH',
                          type=to_unicode,
                          help='Set path to the ffmpeg binary')
    dl_group.add_argument('--ffprobe', metavar='PATH',
                          type=to_unicode,
                          help='Set path to the ffprobe binary')
    dl_group.add_argument('--adobehds', metavar='CMD',
                          type=to_unicode, default='',
                          help='Set command for executing AdobeHDS.php')
    dl_group.add_argument('--wget', metavar='PATH',
                          type=to_unicode, default='',
                          help='Set path to wget binary')

    return parser


def read_urls_from_file(f):
    with codecs.open(f, 'r', 'utf-8') as infile:
        return [x.strip() for x in infile.readlines()]


def encode_url_utf8(url):
    """Encode the path component of url to percent-encoded UTF8."""
    (scheme, netloc, path, params, query, fragment) = urlparse(url)

    # Assume that the path is already encoded if there seems to be
    # percent encoded entities.
    if re.search(r'%[0-9A-Fa-f]{2}', path) is None:
        path = quote(path.encode('UTF8'), '/+')

    return urlunparse((scheme, netloc, path, params, query, fragment))


def download(url, action, io, httpclient, stream_filters, postprocess_command):
    """Parse a web page and download the enclosed stream.

    url is an Areena, Elävä Arkisto or Yle news web page.

    action is one of StreamAction constants that specifies what exactly
    is done with the stream (save to a file, print the title, ...)

    Returns RD_SUCCESS if a stream was successfully downloaded,
    RD_FAIL is no stream was detected or the download failed, or
    RD_INCOMPLETE if a stream was downloaded partially but the
    download was interrupted.
    """
    extractor = extractor_factory(url, stream_filters, httpclient)
    if not extractor:
        logger.error('Unsupported URL %s.' % url)
        logger.error('Is this really a Yle video page?')
        return RD_FAILED

    if action == StreamAction.PRINT_EPISODE_PAGES:
        print_lines(extractor.get_playlist(url))
        return RD_SUCCESS

    clips = extractor.extract(url, stream_filters.latest_only)
    dl = YleDlDownloader(SubtitleDownloader(httpclient))

    if action == StreamAction.PRINT_STREAM_URL:
        print_lines(dl.get_urls(clips, stream_filters))
        return RD_SUCCESS
    elif action == StreamAction.PRINT_STREAM_TITLE:
        print_lines(dl.get_titles(clips, io))
        return RD_SUCCESS
    elif action == StreamAction.PRINT_METADATA:
        print_lines(dl.get_metadata(clips))
        return RD_SUCCESS
    elif action == StreamAction.PIPE:
        return dl.pipe(clips, io, stream_filters)
    elif action == StreamAction.DOWNLOAD_SUBTITLES_ONLY:
        dl.download_subtitles(clips, io, stream_filters)
        return RD_SUCCESS
    else:
        return dl.download_clips(clips, io, stream_filters,
                                 postprocess_command)


def print_lines(lines):
    for line in lines:
        print_enc(line)


def bitrate_from_arg(arg):
    if arg is None:
        return None
    elif arg == 'best':
        return None
    elif arg == 'worst':
        return 0
    else:
        try:
            return int(arg)
        except ValueError:
            logger.warning('Invalid bitrate %s, defaulting to best' % arg)
            return None


def resolution_from_arg(arg):
    if arg is None:
        return None

    if re.match(r'\d+p$', arg):
        arg = arg[:-1]

    try:
        return int(arg)
    except ValueError:
        logger.warning('Invalid resolution: {}'.format(arg))
        return None


### main program ###


def main(argv=sys.argv):
    parser = arg_parser()
    args = parser.parse_args(argv[1:])

    loglevel = logging.DEBUG if args.debug else logging.INFO
    logger.setLevel(loglevel)

    excludechars = '\"*/:<>?|' if args.vfat else '*/|'
    dl_limits = DownloadLimits(args.duration, args.ratelimit)
    io = IOContext(args.outputfile, args.destdir, args.resume,
                   dl_limits, excludechars, args.proxy, args.rtmpdump,
                   args.adobehds, args.ffmpeg, args.ffprobe, args.wget)

    urls = []
    if args.url:
        urls = [encode_url_utf8(args.url)]

    if args.inputfile:
        urls = read_urls_from_file(args.inputfile)

    if not urls:
        parser.print_help()
        sys.exit(RD_SUCCESS)

    if args.showurl:
        action = StreamAction.PRINT_STREAM_URL
    elif args.showepisodepage:
        action = StreamAction.PRINT_EPISODE_PAGES
    elif args.showtitle:
        action = StreamAction.PRINT_STREAM_TITLE
    elif args.showmetadata:
        action = StreamAction.PRINT_METADATA
    elif args.pipe or (args.outputfile == '-'):
        action = StreamAction.PIPE
    elif args.subtitlesonly:
        action = StreamAction.DOWNLOAD_SUBTITLES_ONLY
    else:
        action = StreamAction.DOWNLOAD

    if (action != StreamAction.PIPE and
        (args.debug or not (action in [StreamAction.PRINT_STREAM_URL,
                                       StreamAction.PRINT_STREAM_TITLE,
                                       StreamAction.PRINT_EPISODE_PAGES,
                                       StreamAction.PRINT_METADATA]))):
        print_enc(parser.description)

    backends = Backends.parse_backends(args.backend.split(','))
    if len(backends) == 0:
        sys.exit(RD_FAILED)

    sublang = args.sublang or 'all'
    maxbitrate = bitrate_from_arg(args.maxbitrate)
    maxheight = resolution_from_arg(args.resolution)
    stream_filters = StreamFilters(args.latestepisode, args.audiolang, sublang,
                                   args.hardsubs, maxbitrate, maxheight,
                                   backends)
    httpclient = HttpClient(args.proxy)
    exit_status = RD_SUCCESS

    for i, url in enumerate(urls):
        if args.inputfile:
            logger.info('')
            logger.info('Now downloading from URL {}/{}: {}'.format(
                i + 1, len(urls), url))

        res = download(url, action, io, httpclient, stream_filters,
                       args.postprocess)

        if res != RD_SUCCESS:
            exit_status = res

    return exit_status


if __name__ == '__main__':
    sys.exit(main())
