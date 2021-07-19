# -*- coding: utf-8 -*-

import ctypes
import ctypes.util
import logging
import os
import os.path
import platform
import signal
import shlex
import subprocess
from builtins import str
from .exitcodes import RD_SUCCESS, RD_FAILED, RD_INCOMPLETE, \
    RD_SUBPROCESS_EXECUTE_FAILED
from .http import HttpClient
from .localization import two_letter_language_code
from .utils import ffmpeg_loglevel


logger = logging.getLogger('yledl')


class IOCapability(object):
    RESUME = 'resume'
    PROXY = 'proxy'
    RATELIMIT = 'ratelimit'
    SLICE = 'slice'


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


def shlex_join(elements):
    try:
        return shlex.join(elements)
    except AttributeError:
        # Python older than 3.8 does not have shlex.join
        return ' '.join(elements)


### Base class for downloading a stream to a local file ###


class BaseDownloader(object):
    def __init__(self):
        self.io_capabilities = frozenset()
        self.error_message = None

    def is_valid(self):
        return True

    def warn_on_unsupported_feature(self, io):
        if io.proxy and IOCapability.PROXY not in self.io_capabilities:
            logger.warning('Proxy not supported on this stream. '
                           'Trying to continue anyway')

        if io.download_limits.ratelimit and \
           IOCapability.RATELIMIT not in self.io_capabilities:
            logger.warning('Rate limiting not supported on this stream')

        if io.download_limits.duration and \
           IOCapability.SLICE not in self.io_capabilities:
            logger.warning('--duration will be ignored on this stream')

        if io.download_limits.start_position and \
           IOCapability.SLICE not in self.io_capabilities:
            logger.warning('--startposition will be ignored on this stream')

        # IOCapability.RESUME will be checked later when we know if we
        # are trying to resume a partial download

    def warn_on_unsupported_resume(self, filename, clip, io):
        if (io.resume and
            IOCapability.RESUME not in self.io_capabilities and
            filename != '-' and
            os.path.isfile(filename)
        ):
            logger.warning('Resume not supported on this stream')

    def file_extension(self, preferred):
        return PreferredFileExtension('.mp4')

    def save_stream(self, output_name, clip, io):
        """Deriving classes override this to perform the download"""
        raise NotImplementedError('save_stream must be overridden')

    def pipe(self, io):
        """Derived classes can override this to pipe to stdout"""
        return RD_FAILED

    def stream_url(self):
        """Derived classes can override this to return the URL of the stream"""
        return None

    def full_stream_already_downloaded(self, filename, clip, io):
        ffprobe = io.ffprobe()
        if not ffprobe or not os.path.exists(filename):
            return False

        logger.info('{} already exists.\n'
                    'Checking if the stream is complete...'
                    .format(filename))

        expected_duration = clip.duration_seconds
        if expected_duration is None or expected_duration <= 0:
            return False

        try:
            downloaded_duration = ffprobe.duration_seconds_file(filename)
        except ValueError as ex:
            logger.warning('Failed to get duration for the file'
                           '{}: {}'.format(filename, str(ex)))
            return False

        logger.debug('Downloaded duration {} s, expected {} s'.format(
            downloaded_duration, expected_duration))

        return downloaded_duration >= 0.98 * expected_duration


### Base class for downloading a stream to a file using an external program ###


class ExternalDownloader(BaseDownloader):
    def save_stream(self, output_name, clip, io):
        self.warn_on_unsupported_resume(output_name, clip, io)

        env = self.extra_environment(io)
        args = self.build_args(output_name, clip, io)
        return self.external_downloader([args], env)

    def pipe(self, io):
        commands = [self.build_pipe_args(io)]
        env = self.extra_environment(io)
        return self.external_downloader(commands, env)

    def build_args(self, output_name, clip, io):
        raise NotImplementedError('build_args must be overridden')

    def build_pipe_args(self, io):
        raise NotImplementedError('build_pipe_args must be overridden')

    def extra_environment(self, io):
        return None

    def external_downloader(self, commands, env=None):
        return Subprocess().execute(commands, env)


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
        shell_command_string = ' | '.join(shlex_join(args) for args in commands)
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


### Download a HLS stream by delegating to ffmpeg ###


class HLSBackend(ExternalDownloader):
    def __init__(self, url, long_probe=False, program_id=0, is_live=False):
        ExternalDownloader.__init__(self)
        self.url = url
        self.long_probe = long_probe
        self.program_id = program_id
        self.live = is_live
        self.io_capabilities = frozenset([
            IOCapability.SLICE,
            IOCapability.PROXY
        ])
        self.name = Backends.FFMPEG

    def file_extension(self, preferred):
        ext = preferred if preferred.startswith('.') else '.' + preferred
        return PreferredFileExtension(ext)

    def _duration_arg(self, download_limits):
        if download_limits.duration:
            return ['-t', str(download_limits.duration)]
        else:
            return []

    def _proxy_arg(self, io):
        if io.proxy:
            return ['-http_proxy', io.proxy]
        else:
            return []

    def _seek_position_arg(self, download_limits):
        seekpos = download_limits.start_position
        if seekpos:
            if self.live:
                # Areena seem to have 6 secs/fragment. Can we trust
                # that this is a constant?
                return ['-live_start_index', str(seekpos // 6)]
            else:
                return ['-ss', str(seekpos)]
        else:
            return []

    def _probe_args(self):
        if self.long_probe:
            return ['-probesize', '80000000']
        else:
            return []

    def _metadata_args(self, clip, io):
        if not clip:
            return []

        metadata = []
        if clip.description:
            metadata_spec = '' if self._is_mp4(io) else ':s:v:0'
            metadata += ['-metadata' + metadata_spec,
                         'description=' + clip.description]

        if clip.publish_timestamp:
            metadata += ['-metadata',
                         'creation_time=' + clip.publish_timestamp.isoformat()]

        return metadata

    def _subtitle_args(self, io):
        scodec = 'mov_text' if self._is_mp4(io) else 'srt'

        if io.subtitles == 'none':
            return ['-sn']
        elif io.subtitles == 'all':
            return ['-scodec', scodec,
                    '-map', '0:p:{}:s?'.format(self.program_id)]
        else:
            short_code = two_letter_language_code(io.subtitles) or io.subtitles
            return ['-scodec', scodec,
                    '-map', '0:p:{}:s:m:language:{}?'.format(
                        self.program_id, short_code)]

    def build_args(self, output_name, clip, io):
        args = (['-bsf:a', 'aac_adtstoasc',
                 '-vcodec', 'copy',
                 '-acodec', 'copy'] +
                self._subtitle_args(io) +
                ['-map', '0:p:{}:v'.format(self.program_id),
                 '-map', '0:p:{}:a'.format(self.program_id),
                 '-dn',
                 'file:' + output_name])

        return self.ffmpeg_command_line(clip, io, args)

    def build_pipe_args(self, io):
        args = (['-vcodec', 'copy',
                 '-acodec', 'aac',
                 '-map', '0:p:{}:v'.format(self.program_id),
                 '-map', '0:p:{}:a'.format(self.program_id),
                 '-dn'] +
                self._subtitle_args(io) +
                ['-f', 'matroska', 'pipe:1'])

        return self.ffmpeg_command_line(None, io, args)

    def pipe(self, io):
        commands = [self.build_pipe_args(io)]
        env = self.extra_environment(io)
        return self.external_downloader(commands, env)

    def ffmpeg_command_line(self, clip, io, output_options):
        args = [io.ffmpeg_binary, '-y',
                '-headers', 'X-Forwarded-For: %s\r\n' % io.x_forwarded_for,
                '-loglevel', ffmpeg_loglevel(logger.getEffectiveLevel()),
                '-thread_queue_size', '1024',
                '-seekable', '0', # needed for media ID 67-xxxx streams
                '-strict', 'experimental']  # For decoding webvtt subtitles
        if logger.getEffectiveLevel() <= logging.WARNING:
            args.append('-stats')
        args.extend(self._probe_args())
        args.extend(self._seek_position_arg(io.download_limits))
        args.extend(self._proxy_arg(io))
        args.extend(['-i', self.url])
        args.extend(self._duration_arg(io.download_limits))
        args.extend(self._metadata_args(clip, io))
        args.extend(output_options)
        return args

    def stream_url(self):
        return self.url

    def _is_mp4(self, io):
        return ((io.outputfilename and io.outputfilename.endswith('.mp4')) or
                io.preferred_format in ('mp4', '.mp4'))


class HLSAudioBackend(HLSBackend):
    def __init__(self, url):
        HLSBackend.__init__(self, url, False)

    def file_extension(self, preferred):
        return MandatoryFileExtension('.mp3')

    def build_args(self, output_name, clip, io):
        return self.ffmpeg_command_line(
            clip, io,
            ['-map', '0:4?', '-acodec', 'copy',
             '-f', 'mp3', 'file:' + output_name])

    def build_pipe_args(self, io):
        return self.ffmpeg_command_line(
            None, io,
            ['-map', '0:4?', '-acodec', 'copy',
             '-f', 'mp3', 'pipe:1'])


### Download a plain HTTP file ###


class WgetBackend(ExternalDownloader):
    def __init__(self, url, file_extension):
        ExternalDownloader.__init__(self)
        self.url = url

        if not file_extension:
            logger.warning('Mandatory file extension is missing for URL {}'.format(url))
        self._file_extension = MandatoryFileExtension(file_extension or '')
        self.io_capabilities = frozenset([
            IOCapability.RESUME,
            IOCapability.RATELIMIT,
            IOCapability.PROXY
        ])
        self.name = Backends.WGET

    def file_extension(self, preferred):
        return self._file_extension

    def save_stream(self, output_name, clip, io):
        self.download_external_subtitles(clip.subtitles, output_name, io)

        res = super(WgetBackend, self).save_stream(output_name, clip, io)
        if res != 0 and logger.getEffectiveLevel() >= logging.ERROR:
            logger.error('wget failed! Increase verbosity to see more details.')

        return res

    def download_external_subtitles(self, subtitles, video_file_name, io):
        if io.subtitles == 'none' or not subtitles:
            return
        elif io.subtitles == 'all':
            sub = next((s for s in subtitles if s.lang == 'fin'), subtitles[0])
        else:
            sub = next((s for s in subtitles if s.lang == io.subtitles), None)

        if sub:
            logger.debug('Downloading subtitles for {}'.format(sub.lang))

            destination_file = os.path.splitext(video_file_name)[0] + '.srt'
            HttpClient(io).download_to_file(sub.url, destination_file)

    def build_args(self, output_name, clip, io):
        args = self.shared_wget_args(io, output_name)
        args.extend([
            '--progress=bar',
            '--tries=5',
            '--random-wait'
        ])
        if logger.getEffectiveLevel() >= logging.ERROR:
            # This will hide also errors.
            #
            # wget doesn't have a mode that would show errors but
            # silence all other output:
            # https://savannah.gnu.org/bugs/?33839
            #
            # We will hack around that by checking the exit status and
            # showing a generic error message if necessary.
            args.append('--quiet')
        elif logger.getEffectiveLevel() > logging.INFO:
            args.append('--no-verbose')
        elif logger.getEffectiveLevel() <= logging.WARNING:
            args.append('--show-progress')
        if io.resume:
            args.append('--continue')
        if io.download_limits.ratelimit:
            args.append('--limit-rate={}k'.format(io.download_limits.ratelimit))
        args.append(self.url)
        return args

    def build_pipe_args(self, io):
        return self.shared_wget_args(io, '-') + [self.url]

    def shared_wget_args(self, io, output_filename):
        # Sometimes it seems to be necessary to spoof the user-agent,
        # see the issue #206
        spoofed_user_agent = (
            'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:67.0) '
            'Gecko/20100101 Firefox/67.0')

        return [
            io.wget_binary,
            '-O', output_filename,
            '--no-use-server-timestamps',
            '--user-agent=' + spoofed_user_agent,
            '--header', 'X-Forwarded-For: %s' % io.x_forwarded_for,
            '--timeout=20'
        ]

    def extra_environment(self, io):
        env = None
        if io.proxy:
            if 'https_proxy' in os.environ:
                logger.warning('--proxy ignored because https_proxy environment variable exists')
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

    def save_stream(self, output_name, clip, io):
        logger.error(self.error_message)
        return RD_FAILED

    def pipe(self, io):
        logger.error(self.error_message)
        return RD_FAILED


class Backends(object):
    FFMPEG = 'ffmpeg'
    WGET = 'wget'

    default_order = [
        FFMPEG,
        WGET,
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
