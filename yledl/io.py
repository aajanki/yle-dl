# -*- coding: utf-8 -*-

from __future__ import print_function, absolute_import, unicode_literals
import attr
from pkg_resources import resource_filename


@attr.s
class DownloadLimits(object):
    duration = attr.ib(default=None)
    ratelimit = attr.ib(default=None)


@attr.s
class IOContext(object):
    outputfilename = attr.ib(default=None)
    destdir = attr.ib(default=None)
    resume = attr.ib(default=False)
    download_limits = attr.ib(
        default=None,
        converter=lambda x: x or DownloadLimits()
    )
    excludechars = attr.ib(default='*/|')
    proxy = attr.ib(default=None)
    rtmpdump_binary = attr.ib(default=None)
    hds_binary = attr.ib(
        default=None,
        converter=lambda x: x or ['php', resource_filename(__name__, 'AdobeHDS.php')]
    )
    ffmpeg_binary = attr.ib(default='ffmpeg')
    ffprobe_binary = attr.ib(default='ffprobe')
    wget_binary = attr.ib(default='wget')
