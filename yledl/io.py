# -*- coding: utf-8 -*-

from __future__ import print_function, absolute_import, unicode_literals
from pkg_resources import resource_filename


def normalize_language_code(lang, subtype):
    if lang == 'all' or lang == 'none':
        return lang
    elif subtype == 'hearingimpaired':
        return lang + 'h'
    else:
        language_map = {'fi': 'fin', 'sv': 'swe'}
        return language_map.get(lang, lang)


class DownloadLimits(object):
    def __init__(self, duration=None, ratelimit=None):
        self.duration = duration
        self.ratelimit = ratelimit


class IOContext(object):
    def __init__(self, outputfilename=None, destdir=None, resume=False,
                 dl_limits=DownloadLimits(), excludechars='*/|',
                 proxy=None, rtmpdump_binary=None, hds_binary=None,
                 ffmpeg_binary='ffmpeg', ffprobe_binary='ffprobe',
                 wget_binary='wget'):
        self.outputfilename = outputfilename
        self.destdir = destdir
        self.resume = resume
        self.excludechars = excludechars
        self.proxy = proxy
        self.download_limits = dl_limits

        self.rtmpdump_binary = rtmpdump_binary
        self.ffmpeg_binary = ffmpeg_binary
        self.ffprobe_binary = ffprobe_binary
        self.wget_binary = wget_binary
        if hds_binary:
            self.hds_binary = hds_binary
        else:
            self.hds_binary = \
                ['php', resource_filename(__name__, 'AdobeHDS.php')]


class StreamFilters(object):
    """Parameters for deciding which of potentially multiple available stream
    versions to download.
    """
    def __init__(self, latest_only=False, audiolang='', sublang='all',
                 hardsubs=False, maxbitrate=None, maxheight=None):
        self.latest_only = latest_only
        self.audiolang = audiolang
        self.sublang = sublang
        self.hardsubs = hardsubs
        self.maxbitrate = maxbitrate
        self.maxheight = maxheight

    def sublang_matches(self, langcode, subtype):
        return self._lang_matches(self.sublang, langcode, subtype)

    def audiolang_matches(self, langcode):
        return self.audiolang != '' and \
            self._lang_matches(self.audiolang, langcode, '')

    def _lang_matches(self, langA, langB, subtype):
        return normalize_language_code(langA, '') == \
          normalize_language_code(langB, subtype)
