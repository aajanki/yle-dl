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

import copy
import logging
import os
from attr import asdict
from .errors import TransientDownloadError
from .utils import sane_filename
from .backends import Subprocess
from .errors import ExternalApplicationNotFoundError
from .exitcodes import RD_SUCCESS, RD_FAILED
from .extractors import extractor_factory, url_language
from .localization import TranslationChooser
from .io import OutputFileNameGenerator
from .streamflavor import FailedFlavor


logger = logging.getLogger('yledl')


class YleDlDownloader:
    def __init__(self, geolocation, title_formatter, httpclient,
                 _extractor_factory=extractor_factory):
        self.geolocation = geolocation
        self.title_formatter = title_formatter
        self.httpclient = httpclient
        self.extractor_factory = _extractor_factory

    def download_clips(self, base_url, io, filters):
        extractor = self.extractor_factory(base_url, self.language_chooser(base_url, io),
                                           self.httpclient, self.title_formatter, io.ffprobe())
        if not extractor:
            self.log_unsupported_url_error(base_url)
            return RD_FAILED

        playlist = extractor.get_playlist(base_url, filters.latest_only)

        if len(playlist) > 1 and io.outputfilename is not None:
            logger.error('The source is a playlist with multiple clips, '
                         'but only one output file specified')
            return RD_FAILED
        elif len(playlist) > 1 and extractor.title_formatter.is_constant_pattern():
            logger.error('The source is a playlist with multiple clips, '
                         'but --output-template is a literal: '
                         f'{extractor.title_formatter.template}')
            return RD_FAILED

        if len(playlist) == 0:
            logger.info('No streams found')

        overall_status = RD_SUCCESS
        for clip_url in playlist:
            res = self.download_with_retry(
                clip_url, base_url, extractor, filters, io, max_retry_count=3)
            if res != RD_SUCCESS and overall_status != RD_FAILED:
                overall_status = res

        return overall_status

    def pipe(self, base_url, io, filters):
        extractor = self.extractor_factory(base_url, self.language_chooser(base_url, io),
                                           self.httpclient, self.title_formatter, io.ffprobe())
        if not extractor:
            self.log_unsupported_url_error(base_url)
            return RD_FAILED

        playlist = extractor.get_playlist(base_url)

        if len(playlist) == 0:
            logger.error('No streams found')
            return RD_SUCCESS

        # Can pipe one stream only. Drop other streams if there are more than one.
        clip_url = playlist[0]
        clip = extractor.extract_clip(clip_url, base_url)
        return self.pipe_first_available_stream(clip, filters, io)

    def get_urls(self, base_url, io, filters):
        extractor = self.extractor_factory(base_url, self.language_chooser(base_url, io),
                                           self.httpclient, self.title_formatter, io.ffprobe())
        if not extractor:
            self.log_unsupported_url_error(base_url)
            return []

        clips = extractor.extract(base_url, filters.latest_only)
        for clip in clips:
            streams = self.select_streams(clip.flavors, filters)
            if streams and any(s.is_valid() for s in streams):
                valid_stream = next(s for s in streams if s.is_valid())
                yield valid_stream.stream_url()

    def get_titles(self, base_url, io, latest_only):
        extractor = self.extractor_factory(base_url, self.language_chooser(base_url, io),
                                           self.httpclient, self.title_formatter, io.ffprobe())
        if not extractor:
            self.log_unsupported_url_error(base_url)
            return []

        clips = extractor.extract(base_url, latest_only)
        return (sane_filename(clip.title or '', io.excludechars) for clip in clips)

    def get_metadata(self, base_url, io, latest_only):
        extractor = self.extractor_factory(base_url, self.language_chooser(base_url, io),
                                           self.httpclient, self.title_formatter, io.ffprobe())
        if not extractor:
            self.log_unsupported_url_error(base_url)
            return []

        clips = extractor.extract(base_url, latest_only)
        return list(clip.metadata(io) for clip in clips)

    def get_playlist(self, base_url, io):
        extractor = self.extractor_factory(base_url, self.language_chooser(base_url, io),
                                           self.httpclient, self.title_formatter, io.ffprobe())
        if not extractor:
            self.log_unsupported_url_error(base_url)
            return []

        return extractor.get_playlist(base_url)

    def download_with_retry(self, clip_url, base_url, extractor, filters, io, max_retry_count):
        attempt = 0
        if max_retry_count < 0:
            max_retry_count = 0

        latest_result = RD_FAILED
        while attempt <= max_retry_count:
            if attempt > 0:
                logger.info(f'Retry attempt {attempt} of {max_retry_count}')

            clip = extractor.extract_clip(clip_url, base_url)
            try:
                latest_result = self.download_first_available_stream(clip, filters, io)
            except TransientDownloadError as ex:
                logger.warning(ex.message)

                latest_result = RD_FAILED
                attempt += 1
                continue

            # Download completed
            return latest_result

        # Failed and run out of retry attempts
        return latest_result

    def download_first_available_stream(self, clip, filters, io):
        streams = self.select_streams(clip.flavors, filters) or []
        valid_streams = [s for s in streams if s.is_valid()]

        if not streams:
            logger.error('No stream found')
            return RD_FAILED
        elif not valid_streams:
            logger.error(f'Unsupported stream: {streams[0].error_message}')
            self.print_geo_warning(clip)
            return RD_FAILED

        return self.download_stream(valid_streams, clip, io)

    def download_stream(self, valid_streams, clip, io):
        for stream in valid_streams:
            logger.debug(f'Now trying downloader {stream.name}')

            output_file = self.generate_output_name(clip.title, stream, io)
            try:
                latest_result = self.save_to_file(clip, stream, io, output_file)
            except ExternalApplicationNotFoundError:
                # The downloader subprocess failed to start (a missing application?).
                # Try the next backend.
                continue

            # The backend finished successfully or failed
            return latest_result

        # All backends failed
        return RD_FAILED

    def save_to_file(self, clip, downloader, io, outputfile):
        downloader.warn_on_unsupported_feature(io)

        if not outputfile:
            return RD_FAILED

        if self.should_skip_downloading(outputfile, downloader, clip, io):
            logger.info(f'{outputfile} has already been downloaded.')
            return RD_SUCCESS

        self.log_output_file(outputfile)
        dl_result = downloader.save_stream(outputfile, clip, io)

        if dl_result == RD_SUCCESS:
            self.log_output_file(outputfile, True)
            if io.xattr:
                self.set_extended_file_attributes(outputfile, clip.metadata(io), clip.origin_url)
            self.postprocess(io.postprocess_command, outputfile, [])

        return dl_result

    def pipe_first_available_stream(self, clip, filters, io):
        streams = self.select_streams(clip.flavors, filters) or []
        valid_streams = [s for s in streams if s.is_valid()]

        if not streams:
            logger.error('No stream found')
            return RD_FAILED
        elif not valid_streams:
            logger.error(f'Unsupported stream: {streams[0].error_message}')
            self.print_geo_warning(clip)
            return RD_FAILED

        return self.pipe_stream(valid_streams, clip, io)

    def pipe_stream(self, valid_streams, clip, io):
        for stream in valid_streams:
            logger.debug(f'Now trying downloader {stream.name}')

            stream.warn_on_unsupported_feature(io)

            try:
                return stream.pipe(io)
            except ExternalApplicationNotFoundError:
                # The downloader subprocess failed to start (a missing application?).
                # Try the next backend.
                continue
            except TransientDownloadError:
                # The downloader got started but failed a some point. We have
                # already output something, so we can't switch streams anymore.
                # Just report the error status.
                return RD_FAILED

        # All backends failed
        return RD_FAILED

    def should_skip_downloading(self, outputfile, downloader, clip, io):
        limits = io.download_limits
        slicing_active = limits.start_position or 0 > 0 or limits.duration

        return ((not io.overwrite and os.path.exists(outputfile)) or
                (not slicing_active and
                 downloader.full_stream_already_downloaded(outputfile, clip, io)))

    def generate_output_name(self, title, downloader, io):
        generator = OutputFileNameGenerator()
        extension = downloader.file_extension(io.preferred_format)
        return generator.filename(title, extension, io)

    def select_flavor(self, flavors, filters):
        if not flavors:
            return None

        logger.debug('Available flavors:')
        for fl in flavors:
            logger.debug('bitrate: {bitrate}, height: {height}, '
                         'width: {width}'
                         .format(**asdict(fl)))
        logger.debug('max_height: {maxheight}, max_bitrate: {maxbitrate}'
                     .format(**asdict(filters)))

        filtered = self.apply_backend_filter(flavors, filters)
        filtered = self.apply_resolution_filters(filtered, filters)

        if filtered:
            selected = filtered[-1]
            logger.debug(f'Selected flavor: {selected}')
        else:
            selected = None

        return selected

    def apply_backend_filter(self, flavors, filters):
        def filter_streams_by_backend(flavor):
            sorted_streams = []
            for be in filters.enabled_backends:
                for downloader in flavor.streams:
                    if downloader.name == be:
                        sorted_streams.append(downloader)

            res = copy.copy(flavor)
            res.streams = sorted_streams
            return res

        if not flavors:
            return []

        filtered = [filter_streams_by_backend(fl) for fl in flavors]
        filtered = [fl for fl in filtered if fl.streams]

        if filtered:
            return filtered
        elif flavors:
            return [self.backend_not_enabled_flavor(flavors)]
        else:
            return []

    def apply_resolution_filters(self, flavors, filters):
        def sort_max_bitrate(x):
            return x.bitrate or 0

        def sort_max_resolution_min_bitrate(x):
            return (x.height or 0, -(x.bitrate or 0))

        def sort_max_resolution_max_bitrate(x):
            return (x.height or 0, x.bitrate or 0)

        filtered = [
            fl for fl in flavors
            if (filters.maxbitrate is None or
                (fl.bitrate or 0) <= filters.maxbitrate) and
            (filters.maxheight is None or
             (fl.height or 0) <= filters.maxheight)
        ]

        if filtered:
            acceptable_flavors = filtered
            reverse = False
        else:
            acceptable_flavors = flavors
            reverse = filters.maxheight is not None or filters.maxbitrate is not None

        if filters.maxheight is not None and filters.maxbitrate is not None:
            keyfunc = sort_max_resolution_max_bitrate
        elif filters.maxheight is not None:
            keyfunc = sort_max_resolution_min_bitrate
        else:
            keyfunc = sort_max_bitrate

        return sorted(acceptable_flavors, key=keyfunc, reverse=reverse)

    def backend_not_enabled_flavor(self, flavors):
        supported_backends = set()
        for fl in flavors:
            supported_backends.update(
                s.name for s in fl.streams if s.is_valid())

        error_messages = [s.error_message
                          for fl in flavors
                          for s in fl.streams if not s.is_valid()]

        if supported_backends:
            msg = f'Required backend not enabled. Try: --backend {",".join(supported_backends)}'
        elif error_messages:
            msg = error_messages[0]
        else:
            msg = 'Stream not found'

        return FailedFlavor(msg)

    def error_flavor(self, flavors):
        for fl in flavors:
            for s in fl.streams:
                if not s.is_valid():
                    return FailedFlavor(s.error_message)

        return None

    def select_streams(self, flavors, filters):
        flavor = self.select_flavor(flavors, filters)
        if flavor:
            return flavor.streams or []
        else:
            return None

    def print_geo_warning(self, clip):
        if (
            clip.region in ['Finland', None] and
            not self.geolocation.located_in_finland(clip.webpage)
        ):
            logger.error('This clip is only available in Finland '
                         'and according to Yle you are located abroad')

    def log_output_file(self, outputfile, done=False):
        if outputfile and outputfile != '-':
            if done:
                logger.info(f'Stream saved to {outputfile}')
            else:
                logger.info(f'Output file: {outputfile}')

    def postprocess(self, postprocess_command, videofile, subtitlefiles):
        if postprocess_command:
            args = [postprocess_command, videofile]
            args.extend(subtitlefiles)
            return Subprocess().execute([args], None)

    def log_unsupported_url_error(self, url):
        logger.error(f'Unsupported URL {url}.')
        logger.error('If you think yle-dl should support this page, open a '
                     'bug report at https://github.com/aajanki/yle-dl/issues')

    def language_chooser(self, url, io):
        if io.metadata_language:
            preferred_lang = io.metadata_language
        else:
            preferred_lang = url_language(url)
        return TranslationChooser([preferred_lang])

    def set_extended_file_attributes(self, filename, metadata, referrer_url):
        def xset(name, value_str):
            xa.set(name, value_str.encode('utf-8')[:64*1024])

        try:
            from xattr import xattr
        except ImportError:
            logger.warning("xattr not installed. Extended file attributes won't be set")
            return

        xa = xattr(filename)
        if metadata.get('description'):
            xset('user.dublincore.description', metadata['description'])
        if metadata.get('publish_timestamp'):
            xset('user.dublincore.date', metadata['publish_timestamp'][:10])
        if metadata.get('episode_title'):
            xset('user.dublincore.title', metadata['episode_title'])
        if referrer_url:
            # the requested URL
            xset('user.xdg.referrer.url', referrer_url)
        if metadata.get('webpage'):
            # the final URL
            xset('user.xdg.origin.url', metadata['webpage'])
