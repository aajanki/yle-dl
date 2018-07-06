# -*- coding: utf-8 -*-

from __future__ import print_function, absolute_import, unicode_literals
import codecs
import logging
import os.path
import sys
from .utils import print_enc, sane_filename
from .http import download_to_file
from .backends import Subprocess
from .exitcodes import RD_SUCCESS, RD_FAILED, RD_INCOMPLETE, \
    RD_SUBPROCESS_EXECUTE_FAILED, to_external_rd_code


logger = logging.getLogger('yledl')


class YleDlDownloader(object):
    def __init__(self, backends):
        self.backends = backends

    def download_episodes(self, clips, io, filters, postprocess_command):
        def download(clip, stream):
            downloader = stream.create_downloader(self.backends)
            if not downloader:
                logger.error('Downloading the stream at %s is not yet '
                             'supported.' % clip.webpage)
                logger.error('Try --showurl')
                return RD_FAILED

            clip_title = clip.title or 'ylestream'
            outputfile = downloader.output_filename(clip_title, io)
            downloader.warn_on_unsupported_feature(io)
            selected_subtitles = self.select_subtitles(clip.subtitles, filters)
            subtitlefiles = \
                self.download_subtitles(selected_subtitles, outputfile)
            dl_result = downloader.save_stream(clip_title, io)
            if dl_result == RD_SUCCESS:
                self.postprocess(postprocess_command, outputfile,
                                 subtitlefiles)


            return RD_SUCCESS

        return self.process(clips, download, filters)

    def pipe(self, clips, io, filters):
        def pipe_clip(clip, stream):
            dl = stream.create_downloader(self.backends)
            if not dl:
                logger.error('Downloading the stream at %s is not yet '
                             'supported.' % clip.webpage)
                return RD_FAILED
            dl.warn_on_unsupported_feature(io)
            subtitles = self.select_subtitles(clip.subtitles, filters)
            subtitle_url = subtitles[0].url if subtitles else None
            return dl.pipe(io, subtitle_url)

        return self.process(clips, pipe_clip, filters)

    def print_urls(self, clips, filters):
        def print_url(clip, stream):
            print_enc(stream.to_url())
            return RD_SUCCESS

        return self.process(clips, print_url, filters)

    def print_episode_pages(self, clips, filters):
        for clip in clips:
            print_enc(clip.webpage)

        return RD_SUCCESS

    def print_titles(self, clips, io, filters):
        def print_title(clip, stream):
            print_enc(sane_filename(stream.title, io.excludechars))
            return RD_SUCCESS

        return self.process(clips, print_title, filters)

    def print_metadata(self, clips, filters):
        def print_metadata(clip, stream):
            # FIXME
            return RD_SUCCESS

        return self.process(clips, print_metadata, filters)


    def process(self, clips, streamfunc, filters):
        overall_status = RD_SUCCESS

        for clip in clips:
            stream = self.select_stream(clip.flavors, filters)

            if stream:
                if stream.is_valid():
                    logger.error('Unsupported stream: %s' %
                                 stream.get_error_message())
                    overall_status = RD_FAILED
                else:
                    res = streamfunc(clip, stream)
                    if res != RD_SUCCESS:
                        overall_status = res

        return overall_status

    def select_flavor(self, flavors, filters):
        # FIXME: apply filters
        if flavors:
            return flavors[0]
        else:
            return None

    def select_stream(self, flavors, filters):
        flavor = self.select_flavor(flavors, filters)
        if flavor and flavor.streams:
            stream = flavor.streams[0] # FIXME: select by backend
        else:
            stream = None
        return stream

    def select_subtitles(self, subtitles, filters):
        if filters.hardsubs:
            return []

        selected = []
        for sub in subtitles:
            matching_lang = (filters.sublang_matches(sub.language, '') or
                             filters.sublang == 'all')
            if sub.url and matching_lang:
                selected.append(sub)

        if selected and filters.sublang != 'all':
            selected = selected[:1]

        return selected

    def download_subtitles(self, subtitles, videofilename):
        basename = os.path.splitext(videofilename)[0]
        subtitlefiles = []
        for sub in subtitles:
            filename = basename + '.' + sub.language + '.srt'
            if os.path.isfile(filename):
                logger.debug('Subtitle file {} already exists, skipping'
                             .format(filename))
            else:
                try:
                    download_to_file(sub.url, filename)
                    self.add_BOM(filename)
                    logger.info('Subtitles saved to ' + filename)
                    subtitlefiles.append(filename)
                except IOError:
                    logger.exception('Failed to download subtitles '
                                     'at %s' % sub.url)
        return subtitlefiles

    def add_BOM(self, filename):
        """Add byte-order mark into a file.

        Assumes (but does not check!) that the file is UTF-8 encoded.
        """
        enc = sys.getfilesystemencoding()
        encoded_filename = filename.encode(enc, 'replace')

        with open(encoded_filename, 'rb') as infile:
            content = infile.read()
            if content.startswith(codecs.BOM_UTF8):
                return

        with open(encoded_filename, 'wb') as outfile:
            outfile.write(codecs.BOM_UTF8)
            outfile.write(content)

    def postprocess(self, postprocess_command, videofile, subtitlefiles):
        if postprocess_command:
            args = [postprocess_command, videofile]
            args.extend(subtitlefiles)
            return Subprocess().execute(args, None)
