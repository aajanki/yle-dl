# This file is part of yle-dl.
#
# Copyright 2010-2026 Antti Ajanki and others
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

import logging
import os
import os.path
from typing import AbstractSet, Optional, Iterable, Literal
from .errors import TransientDownloadError
from .exitcodes import RD_SUCCESS, RD_FAILED
from .ffmpeg import optional_stream
from .http import HttpClient
from .localization import two_letter_language_code
from .utils import ffmpeg_loglevel
from .subtitles import delay_subtitles_mkv, delay_substitles_srt
from .subprocess import execute_pipe


logger = logging.getLogger('yledl')

IOCapability = Literal['resume', 'proxy', 'ratelimit', 'slice']


class PreferredFileExtension:
    def __init__(self, extension: str):
        if not extension:
            raise ValueError('extension required')

        self.extension = extension if extension.startswith('.') else '.' + extension
        self.is_mandatory = False


class MandatoryFileExtension:
    def __init__(self, extension: str):
        if not extension:
            raise ValueError('extension required')

        self.extension = extension if extension.startswith('.') else '.' + extension
        self.is_mandatory = True


def exit_code_to_rd(exit_code):
    return RD_SUCCESS if exit_code == 0 else RD_FAILED


### Base class for downloading a stream to a local file ###


class BaseDownloader:
    def __init__(
        self,
        url: str,
        name: str,
        io_capabilities: Optional[Iterable[IOCapability]] = None,
    ):
        self.url = url
        self.name = name
        self.error_message: Optional[str] = None
        self.io_capabilities: AbstractSet[IOCapability] = frozenset(
            io_capabilities or []
        )

    def is_valid(self):
        return True

    def warn_on_unsupported_feature(self, io):
        if io.proxy and 'proxy' not in self.io_capabilities:
            logger.warning(
                'Proxy not supported on this stream. Trying to continue anyway'
            )

        if io.download_limits.ratelimit and 'ratelimit' not in self.io_capabilities:
            logger.warning('Rate limiting not supported on this stream')

        if io.download_limits.duration and 'slice' not in self.io_capabilities:
            logger.warning('--duration will be ignored on this stream')

        if io.download_limits.start_position and 'slice' not in self.io_capabilities:
            logger.warning('--startposition will be ignored on this stream')

        # IOCapability.RESUME will be checked later when we know if we
        # are trying to resume a partial download

    def warn_on_unsupported_resume(self, filename, clip, io):
        if (
            io.resume
            and 'resume' not in self.io_capabilities
            and filename != '-'
            and os.path.isfile(filename)
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
        return self.url

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
        return exit_code_to_rd(execute_pipe(commands, env))


### Base class for downloading by delegating to ffmpeg ###


class FfmpegBackend(ExternalDownloader):
    def build_args(self, output_name: str, clip, io) -> list[str]:
        return (
            [io.ffmpeg_binary]
            + self.input_args(io)
            + self.output_args_file(clip, io, output_name)
        )

    def build_pipe_args(self, io) -> list[str]:
        return [io.ffmpeg_binary] + self.input_args(io) + self.output_args_pipe(io)

    def input_args(self, io) -> list[str]:
        return []

    def output_args_file(self, clip, io, output_name: str) -> list[str]:
        return []

    def output_args_pipe(self, io) -> list[str]:
        return []

    def duration_arg(self, download_limits) -> list[str]:
        if download_limits.duration:
            return ['-t', str(download_limits.duration)]
        else:
            return []

    def proxy_arg(self, io) -> list[str]:
        if io.proxy:
            return ['-http_proxy', io.proxy]
        else:
            return []


### Download an MPEG-DASH and HLS stream by delegating to ffmpeg ###


class DASHHLSBackend(FfmpegBackend):
    def __init__(
        self,
        url: str,
        program_id: Optional[int] = None,
        is_live: bool = False,
    ):
        super().__init__(url, Backends.FFMPEG, ['slice', 'proxy'])
        self.program_id = program_id
        self.live = is_live

    def input_args(self, io):
        args = [
            '-y',
            '-headers',
            f'X-Forwarded-For: {io.x_forwarded_for}\r\n',
            '-loglevel',
            ffmpeg_loglevel(logger.getEffectiveLevel()),
            '-thread_queue_size',
            '2048',
            # -seekable 0 is needed for media ID 67-xxxx streams
            '-seekable',
            '0',
            # -allowed_extensions is required for subtitles starting from ffmpeg
            # versions released since Feb 2025 (e.g. 4.3.9 and 7.1.1).
            # Testing shows that this works also on at least on some older
            # ffmpeg versions, but I haven't checked when -allowed_extensions
            # was introduced.
            '-allowed_extensions',
            'ts,aac,vtt',
        ]
        if not (io.subtitles == 'none' or self.live):
            # Needed for decoding webvtt subtitles on HLS streams
            #
            # Subtitles disabled on live streams, because ffmpeg (at
            # least 4.4) hangs on subtitle detection (Feb 2022).
            args.extend(['-strict', 'experimental'])
        if logger.getEffectiveLevel() <= logging.WARNING:
            args.append('-stats')
        args.extend(self._probe_args())
        args.extend(self._seek_position_arg(io.download_limits))
        args.extend(self.proxy_arg(io))
        args.extend(['-i', self.url])
        return args

    def output_args_pipe(self, io):
        # We don't use "-acodec copy" on pipe, because at least vlc fails to
        # play it failing with "Error parsing AAC extradata, unable to
        # determine samplerate."
        #
        # The reason seems to be that Areena HLS stream doesn't provide AAC
        # extradata but re-transcoding AAC to AAC inserts it.
        return (
            self.duration_arg(io.download_limits)
            + self._map_video_and_audio_streams(io)
            + self._subtitle_args(io)
            + ['-vcodec', 'copy', '-acodec', 'aac', '-dn', '-f', 'matroska', 'pipe:1']
        )

    def output_args_file(self, clip, io, output_name):
        if io.subtitles_only:
            short_code = two_letter_language_code(io.subtitles) or io.subtitles
            return (
                self.duration_arg(io.download_limits)
                + [
                    '-scodec',
                    'srt',
                    '-map',
                    optional_stream(
                        f'0:s:m:language:{short_code}', io.ffmpeg_version()
                    ),
                    '-map',
                    optional_stream(
                        f'0:s:m:language:{io.subtitles}', io.ffmpeg_version()
                    ),
                ]
                + ['-vn', '-an', f'file:{output_name}']
            )
        return (
            self.duration_arg(io.download_limits)
            + self._metadata_args(clip, io)
            + self._map_video_and_audio_streams(io)
            + self._subtitle_args(io)
            + [
                '-bsf:a',
                'aac_adtstoasc',
                '-vcodec',
                'copy',
                '-acodec',
                'copy',
                '-dn',
                f'file:{output_name}',
            ]
        )

    def save_stream(self, output_name, clip, io):
        res = super().save_stream(output_name, clip, io)

        if res == RD_SUCCESS and output_name != '-':
            self._delay_subtitles(output_name, clip, io)

        return res

    def file_extension(self, preferred):
        return PreferredFileExtension(preferred)

    def _seek_position_arg(self, download_limits):
        seekpos = download_limits.start_position
        if seekpos is not None:
            if self.live:
                # Areena seem to have 6 secs/fragment. Can we trust
                # that this is a constant?
                return ['-live_start_index', str(seekpos // 6)]
            else:
                return ['-ss', str(seekpos)]
        else:
            return []

    def _probe_args(self) -> list[str]:
        return [
            '-analyzeduration',
            '10000000',  # 10 seconds
            '-probesize',
            '80000000',  # bytes
        ]

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
                self.program_id = self._select_max_bitrate_video_audio_pid(
                    programs['programs']
                )
            else:
                self.program_id = 0

        return self.program_id

    def _select_max_bitrate_video_audio_pid(self, programs):
        if not programs:
            return 0

        # Find programs that have both video and audio streams
        video_audio_programs = [
            p
            for p in programs
            if {'video', 'audio'}.issubset({s.get('codec_type') for s in p['streams']})
        ]

        programs = video_audio_programs or programs

        # Take the program with the highest bitrate (or the highest
        # program_id if there are no bitrate metadata. Usually the
        # latter programs have higher quality.)
        best = max(
            programs,
            key=lambda p: (
                int(p.get('tags', {}).get('variant_bitrate', 0)),
                p.get('program_id'),
            ),
        )

        return best.get('program_id', 0)

    def _subtitle_args(self, io):
        scodec = 'mov_text' if self._is_mp4(io) else 'srt'
        pid = self._program_id(io)

        if io.subtitles == 'none':
            return ['-sn']
        elif io.subtitles == 'all':
            return [
                '-scodec',
                scodec,
                '-map',
                optional_stream(f'0:p:{pid}:s', io.ffmpeg_version()),
            ]
        else:
            # Sometimes the subtitles are labelled with a two-letter
            # code, sometimes with a three-letter code. Try both.
            short_code = two_letter_language_code(io.subtitles) or io.subtitles
            return [
                '-scodec',
                scodec,
                '-map',
                optional_stream(f'0:s:m:language:{short_code}', io.ffmpeg_version()),
                '-map',
                optional_stream(f'0:s:m:language:{io.subtitles}', io.ffmpeg_version()),
            ]

    def _map_video_and_audio_streams(self, io):
        pid = self._program_id(io)
        return [
            '-map',
            optional_stream(f'0:p:{pid}:v', io.ffmpeg_version()),
            '-map',
            optional_stream(f'0:p:{pid}:a', io.ffmpeg_version()),
        ]

    def _delay_subtitles(self, output_name: str, clip, io) -> None:
        clip_sub_starts: list[float] = [
            x.subtitle_start_time
            for x in clip.flavors
            if x.subtitle_start_time is not None
        ]

        # Prefer subtitle delay set by command line argument --subdelay.
        subtitle_delay_ms = io.subtitle_delay_ms

        if subtitle_delay_ms is None and len(clip_sub_starts) > 0:
            # If --subdelay is not set, use the delay probed from the stream metadata.
            #
            # ffmpeg (at least versions up to 8.1) show subtitles with incorrect timing if the
            # substitle stream has non-zero start time. To fix the timing, we delay subtitles
            # by the probed subtitle stream start time. Taking the minimum of all stream.
            # It should not matter as all streams usually have the same start time.
            subtitle_delay_ms = int(min(clip_sub_starts) * 1000)

        if subtitle_delay_ms:
            if output_name.endswith('.srt'):
                delay_substitles_srt(output_name, subtitle_delay_ms)
            else:
                delay_subtitles_mkv(
                    output_name,
                    subtitle_delay_ms,
                    io.ffmpeg_binary,
                    io.ffmpeg_version(),
                )

    def _is_mp4(self, io):
        return (
            io.outputfilename and io.outputfilename.endswith('.mp4')
        ) or io.preferred_format in ('mp4', '.mp4')

    def full_stream_already_downloaded(self, filename, clip, io):
        if io.subtitles_only:
            return False
        ffprobe = io.ffprobe()
        return ffprobe and ffprobe.full_stream_already_downloaded(
            filename, clip.duration_seconds
        )


### Download an HLS audio stream by delegating to ffmpeg ###


class HLSAudioBackend(FfmpegBackend):
    def __init__(self, url: str):
        super().__init__(url, Backends.FFMPEG, ['slice', 'proxy'])

    def file_extension(self, preferred):
        return MandatoryFileExtension('.mp3')

    def input_args(self, io) -> list[str]:
        args = [
            '-y',
            '-headers',
            f'X-Forwarded-For: {io.x_forwarded_for}\r\n',
            '-loglevel',
            ffmpeg_loglevel(logger.getEffectiveLevel()),
        ]
        if logger.getEffectiveLevel() <= logging.WARNING:
            args.append('-stats')
        args.extend(self._seek_position_arg(io.download_limits))
        args.extend(self.proxy_arg(io))
        args.extend(['-i', self.url])
        return args

    def output_args_file(self, clip, io, output_name: str) -> list[str]:
        return (
            self.duration_arg(io.download_limits)
            + self._metadata_args(clip)
            + ['-f', 'mp3', f'file:{output_name}']
        )

    def output_args_pipe(self, io) -> list[str]:
        return self.duration_arg(io.download_limits) + [
            '-f',
            'mp3',
            'pipe:1',
        ]

    def _seek_position_arg(self, download_limits) -> list[str]:
        if download_limits.start_position is not None:
            return ['-ss', str(download_limits.start_position)]
        else:
            return []

    def _metadata_args(self, clip) -> list[str]:
        if not clip:
            return []

        metadata = []
        if clip.description:
            metadata += [f'description={clip.description}']

        if clip.publish_timestamp:
            metadata += [
                '-metadata',
                f'creation_time={clip.publish_timestamp.isoformat()}',
            ]

        return metadata

    def full_stream_already_downloaded(self, filename, clip, io):
        ffprobe = io.ffprobe()
        return ffprobe and ffprobe.full_stream_already_downloaded(
            filename, clip.duration_seconds
        )


### Download a plain HTTP file ###


class WgetBackend(ExternalDownloader):
    def __init__(self, url, file_extension):
        super().__init__(
            url,
            Backends.WGET,
            ['resume', 'ratelimit', 'proxy'],
        )

        if not file_extension:
            logger.warning(f'Mandatory file extension is missing for URL {url}')
        self._file_extension = MandatoryFileExtension(file_extension)

    def file_extension(self, preferred):
        return self._file_extension

    def save_stream(self, output_name, clip, io):
        if clip is not None:
            self.download_external_subtitles(clip.subtitles, output_name, io)

        if io.subtitles_only:
            return RD_SUCCESS

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
            if io.subtitle_delay_ms:
                delay_substitles_srt(destination_file, io.subtitle_delay_ms)

    def build_args(self, output_name, clip, io):
        args = self.shared_wget_args(io, output_name)
        args.extend(['--progress=bar', '--tries=1', '--random-wait'])
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
            'Gecko/20100101 Firefox/67.0'
        )

        return [
            io.wget_binary,
            '-O',
            output_filename,
            '--no-use-server-timestamps',
            f'--user-agent={spoofed_user_agent}',
            '--header',
            f'X-Forwarded-For: {io.x_forwarded_for}',
            '--timeout=20',
        ]

    def extra_environment(self, io):
        env = None
        if io.proxy:
            if 'https_proxy' in os.environ:
                logger.warning(
                    '--proxy ignored because https_proxy environment variable exists'
                )
            else:
                env = {'https_proxy': io.proxy}
        return env

    def external_downloader(self, commands, env=None):
        res = execute_pipe(commands, env)

        # These exit status codes indicate errors where retrying might help
        # (from the wget man page).
        if res == 3:  # File I/O error
            raise TransientDownloadError('wget: File I/O error')
        elif res == 4:  # Network failure
            raise TransientDownloadError('wget: Network failure')

        return exit_code_to_rd(res)


### Backend representing a failed stream ###


class FailingBackend(BaseDownloader):
    def __init__(self, error_message):
        super().__init__('', '')
        self.error_message = error_message

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
