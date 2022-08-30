# This file is part of yle-dl.
#
# Copyright 2010-2022 Antti Ajanki and others
#
# Yle-dl is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Yle-dl is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with yle-dl. If not, see <https://www.gnu.org/licenses/>.

import ctypes
import ctypes.util
import logging
import os
import os.path
import platform
import signal
import shlex
import subprocess
from .errors import ExternalApplicationNotFoundError, TransientDownloadError
from .exitcodes import RD_SUCCESS, RD_FAILED, RD_INCOMPLETE
from .http import HttpClient
from .localization import two_letter_language_code
from .utils import ffmpeg_loglevel


logger = logging.getLogger('yledl')


class IOCapability:
    RESUME = 'resume'
    PROXY = 'proxy'
    RATELIMIT = 'ratelimit'
    SLICE = 'slice'


class PreferredFileExtension:
    def __init__(self, extension):
        assert extension.startswith('.')
        self.extension = extension
        self.is_mandatory = False


class MandatoryFileExtension:
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


def exit_code_to_rd(exit_code):
    return RD_SUCCESS if exit_code == 0 else RD_FAILED


### Base class for downloading a stream to a local file ###


class BaseDownloader:
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
        if (
            io.resume and
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
        """Override on backends that are able to check if a file is complete."""
        return False


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
        return exit_code_to_rd(Subprocess().execute(commands, env))


class Subprocess:
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
        process = self.start_process(commands, env)
        try:
            return process.wait()
        except KeyboardInterrupt:
            try:
                os.kill(process.pid, signal.SIGINT)
                process.wait()
            except OSError:
                # The process died before we killed it.
                pass
            return RD_INCOMPLETE
        except OSError as exc:
            logger.error(f'Failed to execute {shell_command_string}')
            logger.error(exc.strerror)
            raise ExternalApplicationNotFoundError(f'Failed to execute {shell_command_string}')

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

    def _sigterm_when_parent_dies(self):
        PR_SET_PDEATHSIG = 1

        libcname = ctypes.util.find_library('c')
        libc = libcname and ctypes.CDLL(libcname)

        try:
            libc.prctl(PR_SET_PDEATHSIG, signal.SIGTERM)
        except AttributeError:
            # libc is None or libc does not contain prctl
            pass


### Download a MPEG-DASH and HLS stream by delegating to ffmpeg ###


class DASHHLSBackend(ExternalDownloader):
    def __init__(self, url, long_probe=False, program_id=None,
                 is_live=False, experimental_subtitles=False):
        ExternalDownloader.__init__(self)
        self.url = url
        self.long_probe = long_probe
        self.program_id = program_id
        self.live = is_live
        self.experimental_subtitles = experimental_subtitles
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
            return [
                '-analyzeduration', '10000000',  # 10 seconds
                '-probesize', '80000000',  # bytes
            ]
        else:
            return []

    def _metadata_args(self, clip, io, description_on_video_stream=True):
        if not clip:
            return []

        metadata = []
        if clip.description:
            if description_on_video_stream and not self._is_mp4(io):
                metadata_spec = ':s:v:0'
            else:
                metadata_spec = ''
            metadata += [
                f'-metadata{metadata_spec}',
                f'description={clip.description}',
            ]

        if clip.publish_timestamp:
            metadata += [
                '-metadata',
                f'creation_time={clip.publish_timestamp.isoformat()}',
            ]

        return metadata

    def _program_id(self, io):
        if self.program_id is None:
            ffprobe = io.ffprobe()
            programs = ffprobe.show_programs_for_url(self.url)
            if programs.get('programs'):
                self.program_id = self._select_max_bitrate_video_audio_pid(programs['programs'])
            else:
                self.program_id = 0

        return self.program_id

    def _select_max_bitrate_video_audio_pid(self, programs):
        if not programs:
            return 0

        # Find programs that have both video and audio streams
        video_audio_programs = [
            p for p in programs
            if {'video', 'audio'}.issubset({s.get('codec_type') for s in p['streams']})
        ]

        programs = video_audio_programs or programs

        # Take the program with the highest bitrate (or the highest
        # program_id if there are no bitrate metadata. Usually the
        # latter programs have higher quality.)
        best = max(
            programs,
            key=lambda p: (int(p.get('tags', {}).get('variant_bitrate', 0)), p.get('program_id')))

        return best.get('program_id', 0)

    def _subtitle_args(self, io):
        scodec = 'mov_text' if self._is_mp4(io) else 'srt'
        pid = self._program_id(io)

        if io.subtitles == 'none':
            return ['-sn']
        elif io.subtitles == 'all':
            return ['-scodec', scodec,
                    '-map', f'0:p:{pid}:s?']
        else:
            short_code = two_letter_language_code(io.subtitles) or io.subtitles
            return ['-scodec', scodec,
                    '-map', f'0:p:{pid}:s:m:language:{short_code}?']

    def _map_video_and_audio_streams(self, io):
        pid = self._program_id(io)
        return [
            '-map', f'0:p:{pid}:v?',
            '-map', f'0:p:{pid}:a?'
        ]

    def build_args(self, output_name, clip, io):
        return ([io.ffmpeg_binary] +
                self.input_args(io) +
                self.output_args_file(clip, io, output_name))

    def build_pipe_args(self, io):
        return ([io.ffmpeg_binary] +
                self.input_args(io) +
                self.output_args_pipe(io))

    def pipe(self, io):
        commands = [self.build_pipe_args(io)]
        env = self.extra_environment(io)
        return self.external_downloader(commands, env)

    def input_args(self, io):
        args = [
            '-y',
            '-headers', f'X-Forwarded-For: {io.x_forwarded_for}\r\n',
            '-loglevel', ffmpeg_loglevel(logger.getEffectiveLevel()),
            '-thread_queue_size', '2048',
            '-seekable', '0',  # needed for media ID 67-xxxx streams
        ]
        if not (io.subtitles == 'none' or self.live) and self.experimental_subtitles:
            # Needed for decoding webvtt subtitles on HLS streams
            #
            # Subtitles disabled on live streams, because ffmpeg (at
            # least 4.4) hangs on subtitle detection (Feb 2022).
            args.extend(['-strict', 'experimental'])
        if logger.getEffectiveLevel() <= logging.WARNING:
            args.append('-stats')
        args.extend(self._probe_args())
        args.extend(self._seek_position_arg(io.download_limits))
        args.extend(self._proxy_arg(io))
        args.extend(['-i', self.url])
        return args

    def output_args_pipe(self, io):
        return (
            self._duration_arg(io.download_limits) +
            self._map_video_and_audio_streams(io) +
            self._subtitle_args(io) +
            ['-vcodec', 'copy',
             '-acodec', 'aac',
             '-dn',
             '-f', 'matroska', 'pipe:1']
        )

    def output_args_file(self, clip, io, output_name):
        return (
            self._duration_arg(io.download_limits) +
            self._metadata_args(clip, io) +
            self._map_video_and_audio_streams(io) +
            self._subtitle_args(io) +
            ['-bsf:a', 'aac_adtstoasc',
             '-vcodec', 'copy',
             '-acodec', 'copy',
             '-dn',
             f'file:{output_name}']
        )

    def stream_url(self):
        return self.url

    def _is_mp4(self, io):
        return ((io.outputfilename and io.outputfilename.endswith('.mp4')) or
                io.preferred_format in ('mp4', '.mp4'))

    def full_stream_already_downloaded(self, filename, clip, io):
        ffprobe = io.ffprobe()
        return ffprobe and ffprobe.full_stream_already_downloaded(filename, clip)


class HLSAudioBackend(DASHHLSBackend):
    def __init__(self, url):
        DASHHLSBackend.__init__(self, url)

    def file_extension(self, preferred):
        return MandatoryFileExtension('.mp3')

    def output_args_file(self, clip, io, output_name):
        return (
            self._duration_arg(io.download_limits) +
            self._metadata_args(clip, io, description_on_video_stream=False) +
            ['-acodec', 'copy',
             '-f', 'mp3',
             f'file:{output_name}']
        )

    def output_args_pipe(self, io):
        return (
            self._duration_arg(io.download_limits) +
            ['-acodec', 'copy',
             '-f', 'mp3',
             'pipe:1']
        )

    def full_stream_already_downloaded(self, filename, clip, io):
        ffprobe = io.ffprobe()
        return ffprobe and ffprobe.full_stream_already_downloaded(filename, clip)


### Download a plain HTTP file ###


class WgetBackend(ExternalDownloader):
    def __init__(self, url, file_extension):
        ExternalDownloader.__init__(self)
        self.url = url

        if not file_extension:
            logger.warning(f'Mandatory file extension is missing for URL {url}')
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
        if clip is not None:
            self.download_external_subtitles(clip.subtitles, output_name, io)

        res = super().save_stream(output_name, clip, io)
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
            logger.debug(f'Downloading subtitles for {sub.lang}')
            basename = os.path.splitext(video_file_name)[0]
            destination_file = f'{basename}.srt'
            HttpClient(io).download_to_file(sub.url, destination_file)

    def build_args(self, output_name, clip, io):
        args = self.shared_wget_args(io, output_name)
        args.extend([
            '--progress=bar',
            '--tries=1',
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
            args.append(f'--limit-rate={io.download_limits.ratelimit}k')
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
            f'--user-agent={spoofed_user_agent}',
            '--header', f'X-Forwarded-For: {io.x_forwarded_for}',
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

    def external_downloader(self, commands, env=None):
        res = Subprocess().execute(commands, env)

        # These exit status codes indicate errors where retrying might help
        # (from the wget man page).
        if res == 3:  # File I/O error
            raise TransientDownloadError('wget: File I/O error')
        elif res == 4:  # Network failure
            raise TransientDownloadError('wget: Network failure')

        return exit_code_to_rd(res)

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


class Backends:
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
                logger.warning(f'Invalid backend: {bn}')
                continue

            if bn not in backends:
                backends.append(bn)

        return backends
