#!/usr/bin/env python2
# -*- coding: utf-8 -*-

"""
yle-dl - download videos from Yle servers

Copyright (C) 2010-2017 Antti Ajanki <antti.ajanki@iki.fi>

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

from __future__ import print_function
import sys
import urllib
import re
import os.path
import urlparse
import codecs
import logging
import argparse
from version import version
from utils import print_enc
from downloaders import downloader_factory, StreamFilters, IOContext, \
    BackendFactory, RD_SUCCESS, RD_FAILED


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


def arg_parser():
    class ArgumentParserEncoded(argparse.ArgumentParser):
        def _print_message(self, message, file=None):
            if message:
                if file is None:
                    file = sys.stderr
                print_enc(message, file, False)

    def unicode_arg(bytes):
        return unicode(bytes, sys.getfilesystemencoding())

    description = \
        (u'yle-dl %s: Download media files from Yle Areena and Elävä Arkisto\n'
         u'Copyright (C) 2009-2017 Antti Ajanki <antti.ajanki@iki.fi>, '
         u'license: GPLv3' % version)

    parser = ArgumentParserEncoded(
        description=description,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('-V', '--verbose', '--debug',
                        action='store_true', dest='debug',
                        help='Show verbose debug output')

    io_group = parser.add_argument_group('Input and output')
    url_group = io_group.add_mutually_exclusive_group()
    url_group.add_argument('url', nargs='?', type=unicode_arg,
        help=u'Address of an Areena, Elävä Arkisto, or Yle news web page')
    url_group.add_argument('-i', metavar='FILENAME', dest='inputfile',
                           type=unicode_arg,
                           help='Read input URLs to process from the named '
                           'file, one URL per line')
    io_group.add_argument('-o', metavar='FILENAME', dest='outputfile',
                          type=unicode_arg,
                          help='Save stream to the named file')
    io_group.add_argument('--pipe', action='store_true',
                          help='Dump stream to stdout for piping to media '
                          'player. E.g. "yle-dl --pipe URL | vlc -"')
    io_group.add_argument('--destdir', metavar='DIR',
                          type=unicode_arg,
                          help='Save files to DIR')
    action_group = io_group.add_mutually_exclusive_group()
    action_group.add_argument('--showurl', action='store_true',
                              help="Print URL, don't download")
    action_group.add_argument('--showtitle', action='store_true',
                              help="Print stream title, don't download")
    action_group.add_argument('--showepisodepage', action='store_true',
                              help='Print web page for each episode')
    io_group.add_argument('--vfat', action='store_true',
                          help='Output Windows-compatible filenames')
    io_group.add_argument('--resume', action='store_true',
                          help='Resume a partial download')
    io_group.add_argument('--ratelimit', metavar='BR', type=int,
                          help='Maximum bandwidth consumption, '
                          'interger in kB/s')
    io_group.add_argument('--proxy', metavar='URI',
                          type=unicode_arg,
                          help='Proxy for downloading streams. '
                          'Example: --proxy socks5://localhost:7777')
    io_group.add_argument('--postprocess', metavar='CMD',
                          type=unicode_arg,
                          help='Execute the command CMD after a successful '
                          'download. CMD is called with two arguments: '
                          'video, subtitle')

    qual_group = parser.add_argument_group('Stream type and quality')
    qual_group.add_argument('--audiolang', metavar='LANG',
                            type=unicode_arg,
                            choices=['fin', 'swe'], default='',
                            help='Select stream\'s audio language, "fin" or '
                            '"swe"')
    qual_group.add_argument('--sublang', metavar='LANG',
                            type=unicode_arg,
                            choices=['fin', 'swe', 'smi', 'none', 'all'],
                            help='Download subtitles. LANG is one of "fin", '
                            '"swe", "smi", "none", or "all"')
    qual_group.add_argument('--hardsubs', action='store_true',
                            help='Download stream with hard subs if available')
    qual_group.add_argument('--latestepisode', action='store_true',
                            help='Download the latest episode of a series')
    qual_group.add_argument('--maxbitrate', metavar='RATE',
                            type=unicode_arg,
                            help='Maximum bitrate stream to download, '
                            'integer in kB/s or "best" or "worst". '
                            'Not exact on HDS streams.')
    qual_group.add_argument('--duration', metavar='S', type=int,
                            help='Record only the first S seconds of '
                            'the stream')

    dl_group = parser.add_argument_group('Downloader backends')
    dl_group.add_argument('--backend', metavar='BE',
                          type=unicode_arg,
                          default="adobehdsphp,youtubedl",
                          help='Downloaders that are tried until one of them '
                          ' succeeds (a comma-separated list).\n'
                          'Possible values: '
                          '"adobehdsphp" = AdobeHDS.php, '
                          '"youtubedl" = youtube-dl')
    dl_group.add_argument('--rtmpdump', metavar='PATH',
                          type=unicode_arg,
                          help='Set path to rtmpdump binary')
    dl_group.add_argument('--ffmpeg', metavar='PATH',
                          type=unicode_arg,
                          help='Set path to ffmpeg binary')
    dl_group.add_argument('--adobehds', metavar='CMD',
                          type=unicode_arg, default='',
                          help='Set command for executing AdobeHDS.php')

    return parser


def read_urls_from_file(f):
    with codecs.open(f, 'r', 'utf-8') as infile:
        return [x.strip() for x in infile.readlines()]


def encode_url_utf8(url):
    """Encode the path component of url to percent-encoded UTF8."""
    (scheme, netloc, path, params, query, fragment) = urlparse.urlparse(url)

    path = path.encode('UTF8')

    # Assume that the path is already encoded if there seems to be
    # percent encoded entities.
    if re.search(r'%[0-9A-Fa-f]{2}', path) is None:
        path = urllib.quote(path, '/+')

    return urlparse.urlunparse((scheme, netloc, path, params, query, fragment))


def download(url, action, io, stream_filters, backends, postprocess_command):
    """Parse a web page and download the enclosed stream.

    url is an Areena, Elävä Arkisto or Yle news web page.

    action is one of StreamAction constants that specifies what exactly
    is done with the stream (save to a file, print the title, ...)

    Returns RD_SUCCESS if a stream was successfully downloaded,
    RD_FAIL is no stream was detected or the download failed, or
    RD_INCOMPLETE if a stream was downloaded partially but the
    download was interrupted.
    """
    dl = downloader_factory(url, backends)
    if not dl:
        logger.error(u'Unsupported URL %s.' % url)
        logger.error(u'Is this really a Yle video page?')
        return RD_FAILED

    if action == StreamAction.PRINT_STREAM_URL:
        return dl.print_urls(url, stream_filters)
    elif action == StreamAction.PRINT_EPISODE_PAGES:
        return dl.print_episode_pages(url, stream_filters)
    elif action == StreamAction.PRINT_STREAM_TITLE:
        return dl.print_titles(url, stream_filters)
    elif action == StreamAction.PIPE:
        return dl.pipe(url, io, stream_filters)
    else:
        return dl.download_episodes(url, io, stream_filters,
                                    postprocess_command)


def bitrate_from_arg(arg):
    if arg == 'best':
        return sys.maxint
    elif arg == 'worst':
        return 0
    else:
        try:
            return int(arg)
        except ValueError:
            logger.warning(u'Invalid bitrate %s, defaulting to best' % arg)
            arg = sys.maxint


def which(program):
    """Search for program on $PATH and return the full path if found."""
    # Adapted from http://stackoverflow.com/questions/377017
    def is_exe(fpath):
        return os.path.isfile(fpath) and os.access(fpath, os.X_OK)

    fpath, fname = os.path.split(program)
    if fpath:
        if is_exe(program):
            return program
    else:
        for path in os.environ["PATH"].split(os.pathsep):
            exe_file = os.path.join(path, program)
            if is_exe(exe_file):
                return exe_file

    return None


def find_rtmpdump(rtmpdump_arg):
    binary = rtmpdump_arg

    if not binary:
        if sys.platform == 'win32':
            binary = which('rtmpdump.exe')
        else:
            binary = which('rtmpdump')
    if not binary:
        binary = 'rtmpdump'

    return binary


def find_adobehds(adobehds_arg):
    if adobehds_arg:
        return adobehds_arg.split(' ')
    else:
        return None


def find_ffmpeg(ffmpeg_arg):
    return ffmpeg_arg or 'ffmpeg'


### main program ###


def main():
    parser = arg_parser()
    args = parser.parse_args()

    loglevel = logging.DEBUG if args.debug else logging.INFO
    logger.setLevel(loglevel)

    excludechars = '\"*/:<>?|' if args.vfat else '*/|'
    io = IOContext(args.outputfile, args.destdir, args.resume, args.ratelimit,
                   excludechars, args.proxy, find_rtmpdump(args.rtmpdump),
                   find_adobehds(args.adobehds), find_ffmpeg(args.ffmpeg))

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
    elif args.pipe or (args.outputfile == '-'):
        action = StreamAction.PIPE
    else:
        action = StreamAction.DOWNLOAD

    if (action != StreamAction.PIPE and
        (args.debug or not (action in [StreamAction.PRINT_STREAM_URL,
                                       StreamAction.PRINT_STREAM_TITLE,
                                       StreamAction.PRINT_EPISODE_PAGES]))):
        print_enc(parser.description)

    backends = BackendFactory.parse_backends(args.backend.split(','))
    if len(backends) == 0:
        sys.exit(RD_FAILED)

    if args.sublang:
        sublang = args.sublang
    else:
        sublang = 'none' if action == StreamAction.PIPE else 'all'

    maxbitrate = bitrate_from_arg(args.maxbitrate or sys.maxint)
    stream_filters = StreamFilters(args.latestepisode, args.audiolang, sublang,
                                   args.hardsubs, maxbitrate, args.duration)
    exit_status = RD_SUCCESS

    for url in urls:
        if args.inputfile:
            logger.info('')
            logger.info(u'Now downloading from URL %s:' % url)

        res = download(url, action, io, stream_filters, backends,
                       args.postprocess)

        if res != RD_SUCCESS:
            exit_status = res

    return exit_status


if __name__ == '__main__':
    sys.exit(main())
