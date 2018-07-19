# -*- coding: utf-8 -*-

from __future__ import print_function, absolute_import, unicode_literals
import logging
import os.path
from future.moves.urllib.parse import urlparse
from .backends import RTMPBackend, HLSBackend, HLSAudioBackend, \
    HDSBackend, YoutubeDLHDSBackend, WgetBackend
from .rtmp import create_rtmp_params, rtmp_parameters_to_url, \
    rtmp_parameters_to_rtmpdump_args


logger = logging.getLogger('yledl')


class AreenaStreamBase(object):
    def __init__(self):
        self.error = None
        self.bitrate = None

    def is_valid(self):
        return not self.error

    def get_error_message(self):
        if self.is_valid():
            return None
        else:
            return self.error or 'Stream not valid'

    def to_url(self):
        return ''

    def create_downloader(self):
        return None


class AreenaHDSStream(AreenaStreamBase):
    def __init__(self, hds_url, bitrate, flavor_id):
        AreenaStreamBase.__init__(self)

        self.hds_url = hds_url
        self.bitrate = bitrate
        self.flavor_id = flavor_id

    def to_url(self):
        return self.hds_url

    def create_downloader(self):
        return HDSBackend(self.hds_url, self.bitrate, self.flavor_id)


class AreenaYoutubeDLHDSStream(AreenaHDSStream):
    def create_downloader(self):
        return YoutubeDLHDSBackend(self.hds_url, self.bitrate, self.flavor_id)


class Areena2014RTMPStream(AreenaStreamBase):
    def __init__(self, pageurl, streamurl):
        AreenaStreamBase.__init__(self)
        self.rtmp_params = create_rtmp_params(streamurl, pageurl)

    def is_valid(self):
        return bool(self.rtmp_params)

    def to_url(self):
        return rtmp_parameters_to_url(self.rtmp_params)

    def create_downloader(self):
        args = rtmp_parameters_to_rtmpdump_args(self.rtmp_params)
        if not args:
            return None
        else:
            return RTMPBackend(args)


class HTTPStream(object):
    def __init__(self, url):
        self.url = url
        path = urlparse(url)[2]
        self.ext = os.path.splitext(path)[1] or None
        self.bitrate = None

    def is_valid(self):
        return True

    def get_error_message(self):
        return None

    def to_url(self):
        return self.url

    def create_downloader(self):
        return WgetBackend(self.url, self.ext)


class KalturaHLSStream(HTTPStream):
    def __init__(self, entryid, flavorid, stream_format, ext):
        self.ext = ext
        self.stream_format = stream_format
        self.http_manifest_url = self._manifest_url(
            entryid, flavorid, 'url', ext)
        self.hls_manifest_url = self._manifest_url(
            entryid, flavorid, 'applehttp', '.m3u8')

    def to_url(self):
        if self.stream_format == 'applehttp':
            return self.hls_manifest_url
        else:
            return self.http_manifest_url

    def create_downloader(self):
        return HLSBackend(self.to_url(), self.ext)

    def _manifest_url(self, entry_id, flavor_id, stream_format, manifest_ext):
        return ('https://cdnapisec.kaltura.com/p/1955031/sp/195503100/'
                'playManifest/entryId/{entry_id}/flavorId/{flavor_id}/'
                'format/{stream_format}/protocol/https/a{ext}?'
                'referrer=aHR0cHM6Ly9hcmVlbmEueWxlLmZp'
                '&playSessionId=11111111-1111-1111-1111-111111111111'
                '&clientTag=html5:v2.56&preferredBitrate=600'
                '&uiConfId=37558971'.format(
                    entry_id=entry_id,
                    flavor_id=flavor_id,
                    stream_format=stream_format,
                    ext=manifest_ext))


class KalturaWgetStream(KalturaHLSStream):
    def create_downloader(self):
        return WgetBackend(self.http_manifest_url, self.ext)


class KalturaLiveTVStream(HTTPStream):
    def create_downloader(self):
        return HLSBackend(self.url, '.mp4')


class KalturaLiveAudioStream(HTTPStream):
    def create_downloader(self):
        return HLSAudioBackend(self.url)


class SportsStream(HTTPStream):
    def create_downloader(self):
        return HLSBackend(self.url, '.mp4', long_probe=True)


class InvalidStream(AreenaStreamBase):
    def __init__(self, error_message):
        self.error = error_message
