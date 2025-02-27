#!/usr/bin/env python

"""
yle-dl - download videos from Yle servers

Copyright (C) 2010-2025 Antti Ajanki <antti.ajanki@iki.fi>

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

import sys
import re
import codecs
import json
import logging
import os
import os.path
import configargparse
from urllib.parse import urlparse, urlunparse, parse_qs, quote
from .backends import Backends
from .downloader import YleDlDownloader
from .errors import FfmpegNotFoundError
from .exitcodes import RD_SUCCESS, RD_FAILED
from .geolocation import AreenaGeoLocation
from .http import HttpClient
from .io import IOContext, DownloadLimits, random_elisa_ipv4, get_filesystem_type
from .streamfilters import StreamFilters
from .titleformatter import TitleFormatter
from .utils import print_enc
from .version import __version__


class PlainInfoFormatter(logging.Formatter):
    def format(self, record):
        if record.levelno == logging.INFO:
            return record.getMessage()
        else:
            return super(PlainInfoFormatter, self).format(record)


def yledl_logger():
    logger = logging.getLogger('yledl')
    if (
        not logger.handlers
    ):  # If this logger already has a local handler, don't add another.
        handler = logging.StreamHandler()
        formatter = PlainInfoFormatter('%(levelname)s: %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger


logger = yledl_logger()


class StreamAction:
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

    def open_config_file_and_remember_opened(filename: str, mode: str = 'r'):
        f = open(filename, mode=mode)

        # Track only if the file was opened successfully
        if mode == 'r':
            if hasattr(parser, 'yledl_read_config_files'):
                parser.yledl_read_config_files.append(filename)
            else:
                parser.yledl_read_config_files = [filename]

        return f

    description = (
        f'yle-dl {__version__}: Download media files from Yle Areena and Elävä Arkisto\n'
        'Copyright (C) 2009-2025 Antti Ajanki <antti.ajanki@iki.fi>, license: GPLv3\n'
    )
    xdg_config_home = os.getenv('XDG_CONFIG_HOME') or '~/.config'
    parser = ArgumentParserEncoded(
        default_config_files=['~/.yledl.conf', f'{xdg_config_home}/yledl.conf'],
        config_file_open_func=open_config_file_and_remember_opened,
        description=description,
        formatter_class=configargparse.RawDescriptionHelpFormatter,
    )
    _add_toplevel_arguments(parser)
    _add_io_arguments(parser)
    _add_quality_arguments(parser)
    _add_downloader_arguments(parser)

    return parser


def _add_downloader_arguments(parser):
    dl_group = parser.add_argument_group('Downloader backends')
    dl_group.add_argument(
        '--backend',
        metavar='BE',
        type=str,
        default='ffmpeg,wget',
        help='Downloaders that are tried until one of them succeeds '
        '(a comma-separated list). Possible values: "wget", "ffmpeg"',
    )
    dl_group.add_argument(
        '--ffmpeg',
        metavar='PATH',
        type=str,
        help='Set the path of the ffmpeg executable',
    )
    dl_group.add_argument(
        '--ffprobe',
        metavar='PATH',
        type=str,
        help='Set the path of the ffprobe executable',
    )
    dl_group.add_argument(
        '--wget',
        metavar='PATH',
        type=str,
        default='',
        help='Set the path of the wget executable',
    )


def _add_quality_arguments(parser):
    qual_group = parser.add_argument_group('Stream type and quality')
    qual_group.add_argument(
        '--sublang',
        metavar='LANG',
        type=str,
        choices=['none', 'fin', 'swe', 'all'],
        default='all',
        help='Download subtitles if LANG is "all" (default), "fin" or "swe". '
        'Disable subtitles if LANG is "none".',
    )
    qual_group.add_argument(
        '--metadatalang',
        metavar='LANG',
        type=str,
        choices=['fin', 'swe', 'smi'],
        help='Preferred metadata language, "fin", "swe" or "smi"',
    )
    qual_group.add_argument(
        '--latestepisode',
        action='store_true',
        help='Download the latest episode of a series',
    )
    qual_group.add_argument(
        '--maxbitrate',
        metavar='RATE',
        type=str,
        help='Maximum bitrate stream to download, integer in kB/s or "best" or "worst".',
    )
    qual_group.add_argument(
        '--resolution',
        metavar='RES',
        type=str,
        help='Maximum vertical resolution in pixels, '
        'default: highest available resolution',
    )
    qual_group.add_argument(
        '--startposition',
        metavar='S',
        type=int,
        help='Start recording at S seconds from the start of the stream',
    )
    qual_group.add_argument(
        '--duration',
        metavar='S',
        type=int,
        help='Record only the first S seconds of the stream',
    )
    qual_group.add_argument(
        '--preferformat',
        metavar='F',
        type=str,
        default='mkv',
        help='Preferred video output format: mkv (default) or mp4. Applies only when '
        'downloading with ffmpeg',
    )


def _add_resume_arguments(io_group):
    resume_group = io_group.add_mutually_exclusive_group()
    # --resume is the new default, the option is still accepted but
    # doesn't do anything
    resume_group.add_argument(
        '--resume',
        action='store_true',
        dest='resume',
        default=True,
        help=configargparse.SUPPRESS,
    )
    resume_group.add_argument(
        '--no-resume',
        action='store_false',
        dest='resume',
        help="Don't resume partial files, download the whole stream again",
    )


def _add_action_group_arguments(io_group):
    action_group = io_group.add_mutually_exclusive_group()
    action_group.add_argument(
        '--showurl', action='store_true', help="Print stream URL, don't download"
    )
    action_group.add_argument(
        '--showtitle', action='store_true', help="Print stream title, don't download"
    )
    action_group.add_argument(
        '--showepisodepage', action='store_true', help='Print web page for each episode'
    )
    action_group.add_argument(
        '--showmetadata',
        action='store_true',
        help='Print metadata about available streams',
    )


def _add_io_arguments(parser):
    io_group = parser.add_argument_group('Input and output')
    _add_url_arguments(io_group)
    io_group.add_argument(
        '-o',
        metavar='FILENAME',
        dest='outputfile',
        type=str,
        help='Save stream to the named file',
    )

    _add_action_group_arguments(io_group)

    io_group.add_argument(
        '--output-template',
        metavar='TEMPLATE',
        default='${series_separator}${title}: ${episode_separator}${timestamp}',
        help='Template for generating an output file name '
        'when not using -o. Put the argument in single quotes: '
        "--output-template '${title}'. "
        'The template supports following substitutions: '
        '${title} is replaced by the title of the episode, '
        '${series} is the series title, '
        '${series_separator} is the series title followed by ": ", '
        '${season} is the string "Season XX" where XX is the season, '
        '${episode} is the season and episode number ("S02E12"), '
        '${episode_separator} is the season and episode followed by "-", '
        '${timestamp} is stream publish timestamp ("2018-12-01T18:30"), '
        '${date} is the stream publish date ("2018-12-01"), '
        '${episode_or_date} is the same as "episode", or "date" if the episode '
        'number is unavailable, '
        '${program_id} is an unique ID, '
        '$$ is an escape and will be replaced by a literal $. '
        '/ specifies a subdirectory, but any / in the beginning is removed. '
        'Everything else will appear as-is.',
    )
    io_group.add_argument(
        '--output-na-placeholder',
        metavar='PLACEHOLDER',
        help='Placeholder value for unavailable meta fields '
        'in output filename template (the default is an empty string)',
    )
    io_group.add_argument(
        '--pipe',
        action='store_true',
        help='Dump stream to stdout for piping to media player. '
        'E.g. "yle-dl --pipe URL | vlc -"',
    )
    io_group.add_argument(
        '--destdir', metavar='DIR', type=str, help='Save files to DIR'
    )
    io_group.add_argument(
        '--create-dirs',
        action='store_true',
        default=True,
        help='Create directories automatically (this is the default)',
    )
    io_group.add_argument(
        '--no-create-dirs',
        action='store_false',
        dest='create_dirs',
        help='Stop if an output directory does not exist',
    )
    io_group.add_argument(
        '--restrict-filename-no-spaces',
        action='store_true',
        dest='filenames_no_spaces',
        help='Replace spaces by underscores in generated filenames',
    )
    io_group.add_argument(
        '--restrict-filename-no-specials',
        action='store_true',
        dest='filenames_no_specials',
        help='Generate Windows-compatible filenames by avoiding certain reserved characters',
    )
    io_group.add_argument(
        '--vfat',
        action='store_true',
        dest='filenames_no_specials',
        help='Alias for --restrict-filename-no-specials',
    )

    _add_resume_arguments(io_group)

    io_group.add_argument(
        '--no-overwrite',
        action='store_false',
        dest='overwrite',
        help='Quit if a file already exists',
    )
    io_group.add_argument(
        '--ratelimit',
        metavar='BR',
        type=int,
        help='Maximum bandwidth consumption, integer in kB/s',
    )
    io_group.add_argument(
        '--proxy',
        metavar='URI',
        type=str,
        help='HTTP(S) proxy to use. Example: --proxy localhost:8118',
    )
    io_group.add_argument(
        '--postprocess',
        metavar='CMD',
        type=str,
        help='Execute the command CMD after a successful download. '
        'CMD is called with two arguments: video, subtitle',
    )
    io_group.add_argument(
        '--xattrs',
        action='store_true',
        help="Write metadata to the video file's xattrs",
    )


def _add_url_arguments(io_group):
    url_group = io_group.add_mutually_exclusive_group()
    url_group.add_argument(
        'url',
        nargs='?',
        type=str,
        help='Address of an Areena, Elävä Arkisto, or Yle news web page',
    )
    url_group.add_argument(
        '-i',
        metavar='FILENAME',
        dest='inputfile',
        type=str,
        help='Read input URLs to process from the named file, one URL per line',
    )


def _add_toplevel_arguments(parser):
    parser.add_argument(
        '-V',
        '--verbose',
        action='count',
        dest='verbosity',
        default=0,
        help='Increase output verbosity. -VV is really verbose.',
    )
    parser.add_argument(
        '-v', '--version', action='version', version=f'yle-dl {__version__}'
    )
    parser.add_argument(
        '--debug',
        action='store_const',
        const=2,
        dest='verbosity',
        help='Really verbose output, same as -VV',
    )
    parser.add_argument(
        '-q',
        action='count',
        dest='quietness',
        default=0,
        help='Reduce output verbosity. -qq prints only errors.',
    )
    parser.add_argument(
        '-c',
        '--config',
        metavar='FILENAME',
        is_config_file=True,
        help='config file path',
    )


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


def execute_action(url, action, io, httpclient, title_formatter, stream_filters):
    """Parse a web page and download the enclosed stream.

    url is an Areena, Elävä Arkisto or Yle news web page.

    action is one of StreamAction constants that specifies what exactly
    is done with the stream (save to a file, print the title, ...)

    Returns RD_SUCCESS if a stream was successfully downloaded,
    RD_FAIL is no stream was detected or the download failed, or
    RD_INCOMPLETE if a stream was downloaded partially but the
    download was interrupted.
    """
    dl = YleDlDownloader(AreenaGeoLocation(httpclient), title_formatter, httpclient)

    if action == StreamAction.PRINT_EPISODE_PAGES:
        print_lines(dl.get_playlist(url, io))
        return RD_SUCCESS
    elif action == StreamAction.PRINT_STREAM_URL:
        print_lines(dl.get_urls(url, io, stream_filters))
        return RD_SUCCESS
    elif action == StreamAction.PRINT_STREAM_TITLE:
        print_lines(dl.get_titles(url, io, stream_filters.latest_only))
        return RD_SUCCESS
    elif action == StreamAction.PRINT_METADATA:
        metadata = dl.get_metadata(url, io, stream_filters.latest_only)
        print_enc(json.dumps(metadata, indent=2, ensure_ascii=False))
        return RD_SUCCESS
    elif action == StreamAction.PIPE:
        return dl.pipe(url, io, stream_filters)
    elif action == StreamAction.DOWNLOAD:
        return dl.download_clips(url, io, stream_filters)
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
            logger.warning(f'Invalid bitrate {arg}, defaulting to best')
            return 999999


def resolution_from_arg(arg):
    if arg is None:
        return None

    if re.match(r'\d+p$', arg):
        arg = arg[:-1]

    try:
        return int(arg)
    except ValueError:
        logger.warning(f'Invalid resolution: {arg}')
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


def get_urls(args):
    urls = []

    if args.url:
        urls = [encode_url_utf8(args.url)]

    if args.inputfile:
        urls = read_urls_from_file(args.inputfile)

    return urls


def expanduser(args):
    if args.outputfile is not None:
        args.outputfile = os.path.expanduser(args.outputfile)
    if args.destdir is not None:
        args.destdir = os.path.expanduser(args.destdir)
    if args.postprocess is not None:
        args.postprocess = os.path.expanduser(args.postprocess)
    if args.ffmpeg is not None:
        args.ffmpeg = os.path.expanduser(args.ffmpeg)
    if args.ffprobe is not None:
        args.ffprobe = os.path.expanduser(args.ffprobe)
    if args.wget is not None:
        args.wget = os.path.expanduser(args.wget)

    return args


def start_position_from_url(url):
    p = urlparse(url)
    seeks = parse_qs(p.query).get('seek')
    return int(seeks[0]) if seeks else None


def warn_on_obsolete_ffmpeg(backends, io):
    if 'ffmpeg' in backends:
        version = io.ffmpeg_version()
        if version > (0, 0):
            version_string = '{}.{}'.format(*version)
            logger.debug(f'Detected ffmpeg {version_string}')
            if version < (4, 1):
                logger.warning(
                    f'Your version of ffmpeg ({version_string}) '
                    'might not download all streams correctly.\n'
                    'Please upgrade ffmpeg to version 4.1 or later.'
                )


def warn_on_output_template_syntax_change(title_formatter):
    if title_formatter.maybe_missing_separators():
        logger.warning(
            'The syntax of --output-template has changed! '
            'Insert separator characters in the template if needed'
        )


### main program ###


def main(argv=sys.argv):
    logging.addLevelName(5, 'TRACE')

    parser = arg_parser()
    args = parser.parse_args(argv[1:])
    set_log_level(args)

    config_files = getattr(parser, 'yledl_read_config_files', [])
    if config_files:
        logger.debug(f'Parsed config files: {", ".join(config_files)}')

    args = expanduser(args)

    urls = get_urls(args)
    if not urls:
        parser.print_help()
        sys.exit(RD_SUCCESS)

    if not args.filenames_no_specials:
        destdir = args.destdir or os.getcwd()
        if destdir:
            fstype = get_filesystem_type(destdir).upper()
            if fstype in ['VFAT', 'NTFS']:
                logger.info(
                    f'Automatically enabling --restrict-filename-no-specials '
                    f'because the destination is a {fstype} filesystem'
                )
                args.filenames_no_specials = True

    excludechars = r'\"*/:<>?|' if args.filenames_no_specials else '*/|'
    if args.filenames_no_spaces:
        excludechars += ' '

    dl_limits = DownloadLimits(args.startposition, args.duration, args.ratelimit)
    output_template, template_ext = os.path.splitext(args.output_template)
    preferformat = template_ext.strip('.') or args.preferformat
    title_formatter = TitleFormatter(output_template, args.output_na_placeholder)
    if args.xattrs and sys.platform in ['win32', 'cygwin']:
        logger.warning('--xattrs not supported on Windows')
        args.xattrs = False
    io = IOContext(
        outputfilename=args.outputfile,
        preferred_format=preferformat,
        destdir=args.destdir,
        resume=args.resume,
        overwrite=args.overwrite,
        download_limits=dl_limits,
        excludechars=excludechars,
        proxy=args.proxy,
        x_forwarded_for=random_elisa_ipv4(),
        subtitles=args.sublang,
        metadata_language=args.metadatalang,
        postprocess_command=args.postprocess,
        ffmpeg_binary=args.ffmpeg or 'ffmpeg',
        ffprobe_binary=args.ffprobe or 'ffprobe',
        wget_binary=args.wget or 'wget',
        create_dirs=args.create_dirs,
        xattr=args.xattrs,
    )

    action = _set_sction(args)

    if logger.isEnabledFor(logging.INFO) and action not in [
        StreamAction.PIPE,
        StreamAction.PRINT_STREAM_URL,
        StreamAction.PRINT_STREAM_TITLE,
        StreamAction.PRINT_EPISODE_PAGES,
        StreamAction.PRINT_METADATA,
    ]:
        print_enc(parser.description)

    backends = Backends.parse_backends(args.backend.split(','))
    if len(backends) == 0:
        sys.exit(RD_FAILED)

    maxbitrate = bitrate_from_arg(args.maxbitrate)
    maxheight = resolution_from_arg(args.resolution)
    stream_filters = StreamFilters(args.latestepisode, maxbitrate, maxheight, backends)
    httpclient = HttpClient(io)

    try:
        warn_on_obsolete_ffmpeg(backends, io)
        warn_on_output_template_syntax_change(title_formatter)

        exit_status = handle_urls(
            action, args, httpclient, io, stream_filters, title_formatter, urls
        )
    except FfmpegNotFoundError:
        logger.error('ffmpeg or ffprobe not found on PATH.')
        logger.error(
            'Install ffmpeg, and use "--ffmpeg" and "--ffprobe" '
            'to set the ffmpeg and ffprobe locations'
        )
        logger.error('or use "--backend wget".')
        exit_status = RD_FAILED

    return exit_status


def _set_sction(args):
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
    return action


def handle_urls(action, args, httpclient, io, stream_filters, title_formatter, urls):
    exit_status = RD_SUCCESS

    for i, url in enumerate(urls):
        if len(urls) > 1:
            logger.info('')
            logger.info(f'Now downloading from URL {i + 1}/{len(urls)}: {url}')

        if args.startposition is not None:
            io.download_limits.start_position = args.startposition
        elif start_position_from_url(url) is not None:
            io.download_limits.start_position = start_position_from_url(url)

        res = execute_action(
            url,
            action=action,
            io=io,
            httpclient=httpclient,
            title_formatter=title_formatter,
            stream_filters=stream_filters,
        )

        if res != RD_SUCCESS:
            exit_status = res
    return exit_status


if __name__ == '__main__':
    sys.exit(main())
