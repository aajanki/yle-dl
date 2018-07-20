# -*- coding: utf-8 -*-

from __future__ import print_function, absolute_import, unicode_literals
import ctypes
import ctypes.util
import logging
import os
import os.path
import platform
import re
import signal
import subprocess
from builtins import str
from future.moves.urllib.error import HTTPError
from .exitcodes import RD_SUCCESS, RD_FAILED, RD_INCOMPLETE, \
    RD_SUBPROCESS_EXECUTE_FAILED
from .http import yledl_user_agent
from .io import which
from .rtmp import rtmp_parameters_to_url, rtmp_parameters_to_rtmpdump_args


logger = logging.getLogger('yledl')

class IOCapability(object):
    RESUME = 'resume'
    PROXY = 'proxy'
    RATELIMIT = 'ratelimit'
    DURATION = 'duration'


class PreferredFileExtension(object):
    def __init__(self, extension):
        assert extension.startswith('.')
        self.extension = extension
        self.is_mandatory = False


class MandatoryFileExtension(object):
    def __init__(self, extension):
        assert extension.startswith('.')
        self.extension = extension
        self.is_mandatory = True


### Base class for downloading a stream to a local file ###


class BaseDownloader(object):
    def __init__(self):
        self.file_extension = MandatoryFileExtension('.flv')
        self.io_capabilities = frozenset()
        self.error_message = None

    def is_valid(self):
        return True

    def warn_on_unsupported_feature(self, io):
        if io.resume and IOCapability.RESUME not in self.io_capabilities:
            logger.warn('Resume not supported on this stream')
        if io.proxy and IOCapability.PROXY not in self.io_capabilities:
            logger.warn('Proxy not supported on this stream. '
                        'Trying to continue anyway')
        if io.download_limits.ratelimit and \
           IOCapability.RATELIMIT not in self.io_capabilities:
            logger.warn('Rate limiting not supported on this stream')
        if io.download_limits.duration and \
           IOCapability.DURATION not in self.io_capabilities:
            logger.warning('--duration will be ignored on this stream')

    def save_stream(self, output_name, io):
        """Deriving classes override this to perform the download"""
        raise NotImplementedError('save_stream must be overridden')

    def pipe(self, io, subtitle_url):
        """Derived classes can override this to pipe to stdout"""
        return RD_FAILED

    def stream_url(self):
        """Derived classes can override this to return the URL of the stream"""
        return None


### Download a stream to a file using an external program ###


class ExternalDownloader(BaseDownloader):
    def save_stream(self, output_name, io):
        env = self.extra_environment(io)
        args = self.build_args(output_name, io)
        return self.external_downloader([args], env)

    def pipe(self, io, subtitle_url):
        commands = [self.build_pipe_args(io)]
        env = self.extra_environment(io)
        subtitle_command = self._mux_subtitles_command(io.ffmpeg_binary,
                                                       subtitle_url)
        if subtitle_command:
            commands.append(subtitle_command)
        return self.external_downloader(commands, env)

    def build_args(self, output_name, io):
        return []

    def build_pipe_args(self, io):
        return []

    def extra_environment(self, io):
        return None

    def external_downloader(self, commands, env=None):
        return Subprocess().execute(commands, env)

    def _mux_subtitles_command(self, ffmpeg_binary, subtitle_url):
        if not ffmpeg_binary or not subtitle_url:
            return None

        if which(ffmpeg_binary):
            return [ffmpeg_binary, '-y', '-i', 'pipe:0', '-i', subtitle_url,
                    '-c', 'copy', '-c:s', 'srt', '-f', 'matroska', 'pipe:1']
        else:
            logger.warning('{} not found. Subtitles disabled.'
                           .format(ffmpeg_binary))
            logger.warning('Set the path to ffmpeg using --ffmpeg')
            return None


class Subprocess(object):
    def execute(self, commands, extra_environment):
        """Start external processes connected with pipes and wait completion.

        commands is a list commands to execute. commands[i] is a list of shell
        command and arguments.

        extra_environment is a dict of environment variables that are combined
        with os.environ.
        """
        if not commands:
            return RD_SUCCESS

        logger.debug('Executing:')
        shell_command_string = ' | '.join(' '.join(args) for args in commands)
        logger.debug(shell_command_string)

        env = self.combine_envs(extra_environment)
        try:
            process = self.start_process(commands, env)
            return self.exit_code_to_rd(process.wait())
        except KeyboardInterrupt:
            try:
                os.kill(process.pid, signal.SIGINT)
                process.wait()
            except OSError:
                # The process died before we killed it.
                pass
            return RD_INCOMPLETE
        except OSError as exc:
            logger.error('Failed to execute ' + shell_command_string)
            logger.error(exc.strerror)
            return RD_SUBPROCESS_EXECUTE_FAILED

    def combine_envs(self, extra_environment):
        env = None
        if extra_environment:
            env = dict(os.environ)
            env.update(extra_environment)
        return env

    def start_process(self, commands, env):
        """Start all commands and setup pipes."""
        assert commands

        processes = []
        for i, args in enumerate(commands):
            if i == 0 and platform.system() != 'Windows':
                preexec_fn = self._sigterm_when_parent_dies
            else:
                preexec_fn = None

            stdin = processes[-1].stdout if processes else None
            stdout = None if i == len(commands) - 1 else subprocess.PIPE
            processes.append(subprocess.Popen(
                args, stdin=stdin, stdout=stdout,
                env=env, preexec_fn=preexec_fn))

        # Causes the first process to receive SIGPIPE if the seconds
        # process exists
        for p in processes[:-1]:
            p.stdout.close()

        return processes[0]

    def exit_code_to_rd(self, exit_code):
        return RD_SUCCESS if exit_code == 0 else RD_FAILED

    def _sigterm_when_parent_dies(self):
        PR_SET_PDEATHSIG = 1

        libcname = ctypes.util.find_library('c')
        libc = libcname and ctypes.CDLL(libcname)

        try:
            libc.prctl(PR_SET_PDEATHSIG, signal.SIGTERM)
        except AttributeError:
            # libc is None or libc does not contain prctl
            pass


### Download stream by delegating to rtmpdump ###


class RTMPBackend(ExternalDownloader):
    def __init__(self, rtmp_params):
        ExternalDownloader.__init__(self)
        self.rtmp_params = rtmp_params
        self.io_capabilities = frozenset([
            IOCapability.RESUME,
            IOCapability.DURATION
        ])
        self.name = Backends.RTMPDUMP

    def is_valid(self):
        return bool(self.rtmp_params)

    def save_stream(self, output_name, io):
        # rtmpdump fails to resume if the file doesn't contain at
        # least one audio frame. Remove small files to force a restart
        # from the beginning.
        if io.resume and self.is_small_file(output_name):
            self.remove(output_name)

        return super(RTMPBackend, self).save_stream(output_name, io)

    def build_args(self, output_name, io):
        args = [io.rtmpdump_binary]
        args += rtmp_parameters_to_rtmpdump_args(self.rtmp_params)
        args += ['-o', output_name]
        if io.resume:
            args.append('-e')
        if io.download_limits.duration:
            args.extend(['--stop', str(io.download_limits.duration)])
        return args

    def build_pipe_args(self, io):
        args = [io.rtmpdump_binary]
        args += rtmp_parameters_to_rtmpdump_args(self.rtmp_params)
        args += ['-o', '-']
        return args

    def stream_url(self):
        return rtmp_parameters_to_url(self.rtmp_params)

    def is_small_file(self, filename):
        try:
            return os.path.getsize(filename) < 1024
        except OSError:
            return False

    def remove(self, filename):
        try:
            os.remove(filename)
        except OSError:
            pass


### Download a stream by delegating to AdobeHDS.php ###


class HDSBackend(ExternalDownloader):
    def __init__(self, url, bitrate, flavor_id):
        ExternalDownloader.__init__(self)
        self.url = url
        self.bitrate = bitrate
        self.flavor_id = flavor_id
        self.io_capabilities = frozenset([
            IOCapability.RESUME,
            IOCapability.PROXY,
            IOCapability.DURATION,
            IOCapability.RATELIMIT
        ])
        self.name = Backends.ADOBEHDSPHP

    def _bitrate_option(self, bitrate):
        return ['--quality', str(bitrate)] if bitrate else []

    def _limit_options(self, download_limits):
        options = []

        if download_limits.ratelimit:
            options.extend(['--maxspeed', str(download_limits.ratelimit)])

        if download_limits.duration:
            options.extend(['--duration', str(download_limits.duration)])

        return options

    def build_args(self, output_name, io):
        args = ['--delete', '--outfile', output_name]
        return self.adobehds_command_line(io, args)

    def save_stream(self, output_name, io):
        if (io.resume and output_name != '-' and
            os.path.isfile(output_name) and
            not self.fragments_exist(self.flavor_id)):
            logger.info('{} has already been downloaded.'.format(output_name))
            return RD_SUCCESS
        else:
            return super(HDSBackend, self).save_stream(output_name, io)

    def fragments_exist(self, flavor_id):
        pattern = r'.*_{}_Seg[0-9]+-Frag[0-9]+$'.format(re.escape(flavor_id))
        files = os.listdir('.')
        return any(re.match(pattern, x) is not None for x in files)

    def pipe(self, io, subtitle_url):
        res = super(HDSBackend, self).pipe(io, subtitle_url)
        self.cleanup_cookies()
        return res

    def build_pipe_args(self, io):
        return self.adobehds_command_line(io, ['--play'])

    def adobehds_command_line(self, io, extra_args):
        args = list(io.hds_binary)
        args.append('--manifest')
        args.append(self.url)
        args.extend(self._bitrate_option(self.bitrate))
        args.extend(self._limit_options(io.download_limits))
        if io.proxy:
            args.append('--proxy')
            args.append(io.proxy)
            args.append('--fproxy')
        if logger.isEnabledFor(logging.DEBUG):
            args.append('--debug')
        if extra_args:
            args.extend(extra_args)
        return args

    def stream_url(self):
        return self.url

    def cleanup_cookies(self):
        try:
            os.remove('Cookies.txt')
        except OSError:
            pass


### Download a stream delegating to the youtube_dl HDS downloader ###


class YoutubeDLHDSBackend(BaseDownloader):
    def __init__(self, url, bitrate, flavor_id):
        BaseDownloader.__init__(self)
        self.url = url
        self.bitrate = bitrate
        self.io_capabilities = frozenset([
            IOCapability.RESUME,
            IOCapability.PROXY,
            IOCapability.RATELIMIT
        ])
        self.name = Backends.YOUTUBEDL

    def save_stream(self, output_name, io):
        return self._execute_youtube_dl(output_name, io)

    def pipe(self, io, subtitle_url):
        # TODO: subtitles
        return self._execute_youtube_dl('-', io)

    def stream_url(self):
        return self.url

    def _execute_youtube_dl(self, outputfile, io):
        try:
            import youtube_dl
        except ImportError:
            logger.error('Failed to import youtube_dl')
            return RD_FAILED

        ydlopts = {
            'logtostderr': True,
            'proxy': io.proxy,
            'verbose': logger.isEnabledFor(logging.DEBUG)
        }

        dlopts = {
            'nopart': True,
            'continuedl': outputfile != '-' and io.resume
        }
        dlopts.update(self._ratelimit_parameter(io.download_limits.ratelimit))

        ydl = youtube_dl.YoutubeDL(ydlopts)
        f4mdl = youtube_dl.downloader.F4mFD(ydl, dlopts)
        info = {'url': self.url}
        info.update(self._bitrate_parameter(self.bitrate))
        try:
            if not f4mdl.download(outputfile, info):
                return RD_FAILED
        except HTTPError:
            logger.exception('HTTP request failed')
            return RD_FAILED

        return RD_SUCCESS

    def _bitrate_parameter(self, bitrate):
        return {'tbr': bitrate} if bitrate else {}

    def _ratelimit_parameter(self, ratelimit):
        return {'ratelimit': ratelimit*1024} if ratelimit else {}


### Download a HLS stream by delegating to ffmpeg ###


class HLSBackend(ExternalDownloader):
    def __init__(self, url, extension, long_probe=False):
        ExternalDownloader.__init__(self)
        self.url = url
        self.file_extension = PreferredFileExtension(extension)
        self.long_probe = long_probe
        self.io_capabilities = frozenset([IOCapability.DURATION])
        self.name = Backends.FFMPEG

    def _duration_arg(self, download_limits):
        if download_limits.duration:
            return ['-t', str(download_limits.duration)]
        else:
            return []

    def _probe_args(self):
        if self.long_probe:
            return ['-probesize', '80000000']
        else:
            return []

    def build_args(self, output_name, io):
        return self.ffmpeg_command_line(
            io,
            ['-bsf:a', 'aac_adtstoasc', '-vcodec', 'copy',
             '-acodec', 'copy', 'file:' + output_name])

    def build_pipe_args(self, io):
        return self.ffmpeg_command_line(
            io,
            ['-vcodec', 'copy', '-acodec', 'copy',
             '-f', 'mpegts', 'pipe:1'])

    def build_pipe_with_subtitles_args(self, io, subtitle_url):
        return self.ffmpeg_command_line(
            io,
            ['-thread_queue_size', '512', '-i', subtitle_url,
             '-vcodec', 'copy', '-acodec', 'aac', '-scodec', 'copy',
             '-f', 'matroska', 'pipe:1'])

    def pipe(self, io, subtitle_url):
        if subtitle_url:
            commands = [self.build_pipe_with_subtitles_args(io, subtitle_url)]
        else:
            commands = [self.build_pipe_args(io)]
        env = self.extra_environment(io)
        return self.external_downloader(commands, env)

    def ffmpeg_command_line(self, io, output_options):
        debug = logger.isEnabledFor(logging.DEBUG)
        loglevel = 'info' if debug else 'error'
        args = [io.ffmpeg_binary, '-y',
                '-loglevel', loglevel, '-stats',
                '-thread_queue_size', '512']
        args.extend(self._probe_args())
        args.extend(['-i', self.url])
        args.extend(self._duration_arg(io.download_limits))
        args.extend(output_options)
        return args

    def stream_url(self):
        return self.url


class HLSAudioBackend(HLSBackend):
    def __init__(self, url):
        HLSBackend.__init__(self, url, '.mp3', False)

    def build_args(self, output_name, io):
        return self.ffmpeg_command_line(
            io, ['-map', '0:4?', '-f', 'mp3', 'file:' + output_name])

    def build_pipe_args(self, io):
        return self.ffmpeg_command_line(
            io, ['-map', '0:4?', '-f', 'mp3', 'pipe:1'])


### Download a plain HTTP file ###


class WgetBackend(ExternalDownloader):
    def __init__(self, url, file_extension):
        ExternalDownloader.__init__(self)
        self.url = url
        self.file_extension = MandatoryFileExtension(file_extension)
        self.io_capabilities = frozenset([
            IOCapability.RESUME,
            IOCapability.RATELIMIT,
            IOCapability.PROXY
        ])
        self.name = Backends.WGET

    def build_args(self, output_name, io):
        args = self.shared_wget_args(io.wget_binary, output_name)
        args.extend([
            '--progress=bar',
            '--tries=5',
            '--random-wait'
        ])
        if io.resume:
            args.append('-c')
        if io.download_limits.ratelimit:
            args.append('--limit-rate={}k'.format(io.download_limits.ratelimit))
        args.append(self.url)
        return args

    def build_pipe_args(self, io):
        return self.shared_wget_args(io.wget_binary, '-') + [self.url]

    def shared_wget_args(self, wget_binary, output_filename):
        return [
            wget_binary,
            '-O', output_filename,
            '--no-use-server-timestamps',
            '--user-agent=' + yledl_user_agent(),
            '--timeout=20'
        ]

    def extra_environment(self, io):
        env = None
        if io.proxy:
            if 'https_proxy' in os.environ:
                logger.warn('--proxy ignored because https_proxy environment variable exists')
            else:
                env = {'https_proxy': io.proxy}
        return env

    def stream_url(self):
        return self.url


### Backend representing a failed stream ###


class FailingBackend(BaseDownloader):
    def __init__(self, error_message):
        BaseDownloader.__init__(self)
        self.error_message = error_message
        self.name = None

    def is_valid(self):
        return False

    def save_stream(self, output_name, io):
        logger.error(self.error_message)
        return RD_FAILED

    def pipe(self, io, subtitle_url):
        logger.error(self.error_message)
        return RD_FAILED


class Backends(object):
    ADOBEHDSPHP = 'adobehdsphp'
    YOUTUBEDL = 'youtubedl'
    RTMPDUMP = 'rtmpdump'
    FFMPEG = 'ffmpeg'
    WGET = 'wget'

    default_order = [
        WGET,
        FFMPEG,
        ADOBEHDSPHP,
        YOUTUBEDL,
        RTMPDUMP
    ]

    @staticmethod
    def is_valid_backend(backend_name):
        return backend_name in Backends.default_order

    @staticmethod
    def parse_backends(backend_names):
        backends = []
        for bn in backend_names:
            if not Backends.is_valid_backend(bn):
                logger.warning('Invalid backend: ' + bn)
                continue

            if bn not in backends:
                backends.append(bn)

        return backends
