#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
yle-dl - download videos from Yle servers

Copyright (C) 2010-2020 Antti Ajanki <antti.ajanki@iki.fi>

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
from .downloader import YleDlDownloader
from .exitcodes import RD_SUCCESS, RD_FAILED
from .extractors import extractor_factory, url_language
from .geolocation import AreenaGeoLocation
from .http import HttpClient
from .io import IOContext, DownloadLimits
from .localization import TranslationChooser
from .streamfilters import StreamFilters
from .titleformatter import TitleFormatter
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
         'Copyright (C) 2009-2020 Antti Ajanki <antti.ajanki@iki.fi>, '
         'license: GPLv3\n' % version)

    parser = ArgumentParserEncoded(
        default_config_files=['~/.yledl.conf'],
        description=description,
        formatter_class=configargparse.RawDescriptionHelpFormatter)
    parser.add_argument('-V', '--verbose',
                        action='count', dest='verbosity', default=0,
                        help='Increase output verbosity. -VV is really verbose.')
    parser.add_argument('--debug', action='store_const', const=2,
                        dest='verbosity',
                        help='Really verbose output, same as -VV')
    parser.add_argument('-q', action='count', dest='quietness', default=0,
                        help='Reduce output verbosity. -qq prints only errors.')
    parser.add_argument('-c', '--config', metavar='FILENAME',
                        is_config_file=True, help='config file path')

    io_group = parser.add_argument_group('Input and output')
    url_group = io_group.add_mutually_exclusive_group()
    url_group.add_argument('url', nargs='?', type=to_unicode,
                           help='Address of an Areena, Elävä Arkisto, '
                           'or Yle news web page')
    url_group.add_argument('-i', metavar='FILENAME', dest='inputfile',
                           type=to_unicode,
                           help='Read input URLs to process from the named '
                           'file, one URL per line')
    io_group.add_argument('-o', metavar='FILENAME', dest='outputfile',
                          type=to_unicode,
                          help='Save stream to the named file')
    io_group.add_argument('--output-template', metavar='TEMPLATE',
                          default='${series}${title}${episode}${timestamp}',
                          help='Template for generating an output file name '
                          'when not using -o. The template supports following '
                          'substitutions: '
                          '${title} is replaced by the title of the episode, '
                          '${series} is the series title, '
                          '${episode} is the season and episode number "S02E12", '
                          '${timestamp} is stream publish timestamp "2018-12-01T18:30", '
                          '${date} is the stream publish date "2018-12-01", '
                          '${program_id} is an unique ID, '
                          '$$ is an escape and will be replaced by a literal "$". '
                          'Everything else will appear as-is.')
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
    io_group.add_argument('--vfat', action='store_true',
                          help='Output Windows-compatible filenames')
    resume_group = io_group.add_mutually_exclusive_group()
    # --resume is the new default, the option is still accepted but
    # doesn't do anything
    resume_group.add_argument('--resume', action='store_true',
                              dest='resume', default=True,
                              help=configargparse.SUPPRESS)
    resume_group.add_argument('--no-resume', action='store_false',
                              dest='resume',
                              help='Don\'t resume partial files, '
                              'download the whole stream again')
    io_group.add_argument('--no-overwrite', action='store_false',
                          dest='overwrite',
                          help='Quit if a file already exists')
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
    qual_group.add_argument('--sublang', metavar='LANG',
                            type=to_unicode,
                            choices=['none', 'all'],
                            default='all',
                            help='Download subtitles if LANG is "all" '
                            '(default) or disable subtitles if LANG is "none".')
    qual_group.add_argument('--metadatalang', metavar='LANG', type=to_unicode,
                            choices=['fin', 'swe', 'smi'],
                            help='Preferred metadata language, "fin", "swe" '
                            'or "smi"')
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
    qual_group.add_argument('--preferformat', metavar='F', type=to_unicode,
                            default='mkv',
                            help='Preferred video output format: '
                            'mkv (default) or mp4. Applies only when '
                            'downloading with ffmpeg')

    dl_group = parser.add_argument_group('Downloader backends')
    dl_group.add_argument('--backend', metavar='BE',
                          type=to_unicode,
                          default="ffmpeg,wget",
                          help='Downloaders that are tried until one of them '
                          ' succeeds (a comma-separated list). '
                          'Possible values: '
                          '"wget", '
                          '"ffmpeg"')
    dl_group.add_argument('--ffmpeg', metavar='PATH',
                          type=to_unicode,
                          help='Set path to the ffmpeg binary')
    dl_group.add_argument('--ffprobe', metavar='PATH',
                          type=to_unicode,
                          help='Set path to the ffprobe binary')
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


def download(url, action, io, httpclient, title_formatter, stream_filters,
             postprocess_command, metadatalang):
    """Parse a web page and download the enclosed stream.

    url is an Areena, Elävä Arkisto or Yle news web page.

    action is one of StreamAction constants that specifies what exactly
    is done with the stream (save to a file, print the title, ...)

    Returns RD_SUCCESS if a stream was successfully downloaded,
    RD_FAIL is no stream was detected or the download failed, or
    RD_INCOMPLETE if a stream was downloaded partially but the
    download was interrupted.
    """
    if metadatalang:
        preferred_meta_langs = [metadatalang]
    else:
        preferred_meta_langs = [url_language(url)]
    language_chooser = TranslationChooser(preferred_meta_langs)

    extractor = extractor_factory(
        url, stream_filters, language_chooser, httpclient)
    if not extractor:
        logger.error('Unsupported URL %s.' % url)
        logger.error('Is this really a Yle video page?')
        return RD_FAILED

    if action == StreamAction.PRINT_EPISODE_PAGES:
        print_lines(extractor.get_playlist(url))
        return RD_SUCCESS

    clips = extractor.extract(url, stream_filters.latest_only,
                              title_formatter, io.ffprobe())
    dl = YleDlDownloader(AreenaGeoLocation(httpclient))

    if action == StreamAction.PRINT_STREAM_URL:
        print_lines(dl.get_urls(clips, stream_filters))
        return RD_SUCCESS
    elif action == StreamAction.PRINT_STREAM_TITLE:
        print_lines(dl.get_titles(clips, io))
        return RD_SUCCESS
    elif action == StreamAction.PRINT_METADATA:
        print_lines(dl.get_metadata(clips, io))
        return RD_SUCCESS
    elif action == StreamAction.PIPE:
        return dl.pipe(clips, io, stream_filters)
    elif (action == StreamAction.DOWNLOAD and
          len(clips) > 1 and
          io.outputfilename is not None):
        logger.error('Source contains multiple clips, '
                     'but only one output file specified')
        return RD_FAILED
    elif action == StreamAction.DOWNLOAD:
        return dl.download_clips(clips, io, stream_filters,
                                 postprocess_command)
    else:
        logger.error('Internal error: Unknown action')
        return RD_FAILED


def print_lines(lines):
    for line in lines:
        print_enc(line)


def bitrate_from_arg(arg):
    if arg is None:
        return None
    elif arg == 'best':
        return 999999
    elif arg == 'worst':
        return 0
    else:
        try:
            return int(arg)
        except ValueError:
            logger.warning('Invalid bitrate %s, defaulting to best' % arg)
            return 999999


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


def set_log_level(args):
    verbosity = args.verbosity - args.quietness

    if verbosity <= -2:
        logger.setLevel(logging.ERROR)
    elif verbosity == -1:
        logger.setLevel(logging.WARNING)
    elif verbosity == 0:
        logger.setLevel(logging.INFO)
    elif verbosity == 1:
        logger.setLevel(logging.DEBUG)
    elif verbosity >= 2:
        logger.setLevel(5)


### main program ###


def main(argv=sys.argv):
    logging.addLevelName(5, 'TRACE')

    parser = arg_parser()
    args = parser.parse_args(argv[1:])
    set_log_level(args)

    excludechars = '\"*/:<>?|' if args.vfat else '*/|'
    dl_limits = DownloadLimits(args.duration, args.ratelimit)
    io = IOContext(args.outputfile, args.preferformat, args.destdir,
                   args.resume, args.overwrite, dl_limits, excludechars,
                   args.proxy, args.sublang == 'all',
                   args.ffmpeg, args.ffprobe, args.wget)

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
    else:
        action = StreamAction.DOWNLOAD

    if (logger.isEnabledFor(logging.INFO) and
        action not in [StreamAction.PIPE,
                       StreamAction.PRINT_STREAM_URL,
                       StreamAction.PRINT_STREAM_TITLE,
                       StreamAction.PRINT_EPISODE_PAGES,
                       StreamAction.PRINT_METADATA]):
        print_enc(parser.description)

    backends = Backends.parse_backends(args.backend.split(','))
    if len(backends) == 0:
        sys.exit(RD_FAILED)

    maxbitrate = bitrate_from_arg(args.maxbitrate)
    maxheight = resolution_from_arg(args.resolution)
    stream_filters = StreamFilters(args.latestepisode,
                                   maxbitrate, maxheight, backends)
    httpclient = HttpClient(args.proxy)
    title_formatter = TitleFormatter(args.output_template)
    exit_status = RD_SUCCESS

    for i, url in enumerate(urls):
        if args.inputfile:
            logger.info('')
            logger.info('Now downloading from URL {}/{}: {}'.format(
                i + 1, len(urls), url))

        res = download(url, action, io, httpclient, title_formatter,
                       stream_filters, args.postprocess, args.metadatalang)

        if res != RD_SUCCESS:
            exit_status = res

    return exit_status


if __name__ == '__main__':
    sys.exit(main())
