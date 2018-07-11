# -*- coding: utf-8 -*-

from __future__ import print_function, absolute_import, unicode_literals
import attr
import logging
import os.path
import xml.dom.minidom
from future.moves.urllib.parse import urlparse
from .backends import RTMPBackend, HLSBackend, HLSAudioBackend, \
    HDSBackend, YoutubeDLHDSBackend, WgetBackend
from .http import download_page


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
    # Extracted from
    # http://areena.yle.fi/static/player/1.2.8/flowplayer/flowplayer.commercial-3.2.7-encrypted.swf
    AES_KEY = b'hjsadf89hk123ghk'

    def __init__(self, pageurl, streamurl):
        AreenaStreamBase.__init__(self)
        rtmpstream = self.create_rtmpstream(streamurl)
        self.rtmp_params = self.stream_to_rtmp_parameters(rtmpstream, pageurl,
                                                          False)
        if self.rtmp_params is not None:
            self.rtmp_params['app'] = self.rtmp_params['app'].split('/', 1)[0]

    def create_rtmpstream(self, streamurl):
        (rtmpurl, playpath, ext) = \
            self.parse_rtmp_single_component_app(streamurl)
        playpath = playpath.split('?', 1)[0]
        return PAPIStream(streamurl, playpath)

    def is_valid(self):
        return bool(self.rtmp_params)

    def to_url(self):
        return self.rtmp_parameters_to_url(self.rtmp_params)

    def to_rtmpdump_args(self):
        if self.rtmp_params:
            return self.rtmp_parameters_to_rtmpdump_args(self.rtmp_params)
        else:
            return []

    def create_downloader(self):
        args = self.to_rtmpdump_args()
        if not args:
            return None
        else:
            return RTMPBackend(args)

    def stream_to_rtmp_parameters(self, stream, pageurl, islive):
        if not stream:
            return None

        rtmp_connect = stream.connect
        rtmp_stream = stream.stream
        if not rtmp_stream:
            logger.error('No rtmp stream')
            return None

        try:
            scheme, edgefcs, rtmppath = self.rtmpurlparse(rtmp_connect)
        except ValueError:
            logger.exception('Failed to parse RTMP URL')
            return None

        ident = download_page('http://%s/fcs/ident' % edgefcs)
        if ident is None:
            logger.exception('Failed to read ident')
            return None

        logger.debug(ident)

        try:
            identxml = xml.dom.minidom.parseString(ident)
        except Exception:
            logger.exception('Invalid ident response')
            return None

        nodelist = identxml.getElementsByTagName('ip')
        if len(nodelist) < 1 or len(nodelist[0].childNodes) < 1:
            logger.error('No <ip> node!')
            return None
        rtmp_ip = nodelist[0].firstChild.nodeValue

        app_without_fcsvhost = rtmppath.lstrip('/')
        app_fields = app_without_fcsvhost.split('?', 1)
        baseapp = app_fields[0]
        if len(app_fields) > 1:
            auth = app_fields[1]
        else:
            auth = ''
        app = '%s?_fcs_vhost=%s&%s' % (baseapp, edgefcs, auth)
        rtmpbase = '%s://%s/%s' % (scheme, edgefcs, baseapp)
        tcurl = '%s://%s/%s' % (scheme, rtmp_ip, app)

        areena_swf = ('https://areena.yle.fi/static/player/1.2.8/flowplayer/'
                      'flowplayer.commercial-3.2.7-encrypted.swf')
        rtmpparams = {'rtmp': rtmpbase,
                      'app': app,
                      'playpath': rtmp_stream,
                      'tcUrl': tcurl,
                      'pageUrl': pageurl,
                      'swfUrl': areena_swf}
        if islive:
            rtmpparams['live'] = '1'

        return rtmpparams

    def rtmpurlparse(self, url):
        if '://' not in url:
            raise ValueError("Invalid RTMP URL")

        scheme, rest = url.split('://', 1)
        rtmp_scemes = ['rtmp', 'rtmpe', 'rtmps', 'rtmpt', 'rtmpte', 'rtmpts']
        if scheme not in rtmp_scemes:
            raise ValueError("Invalid scheme in RTMP URL")

        if '/' not in rest:
            raise ValueError("No separator in RTMP URL")

        server, app_and_playpath = rest.split('/', 1)
        return (scheme, server, app_and_playpath)

    def parse_rtmp_single_component_app(self, rtmpurl):
        """Extract single path-component app and playpath from rtmpurl."""
        # YLE server requires that app is the first path component
        # only. By default librtmp would take the first two
        # components (app/appInstance).
        #
        # This also means that we can't rely on librtmp's playpath
        # parser and have to duplicate the logic here.
        k = 0
        if rtmpurl.find('://') != -1:
            i = -1
            for i, x in enumerate(rtmpurl):
                if x == '/':
                    k += 1
                    if k == 4:
                        break

            playpath = rtmpurl[(i+1):]
            app_only_rtmpurl = rtmpurl[:i]
        else:
            playpath = rtmpurl
            app_only_rtmpurl = ''

        ext = os.path.splitext(playpath)[1]
        if ext == '.mp4':
            playpath = 'mp4:' + playpath
            ext = '.flv'
        elif ext == '.mp3':
            playpath = 'mp3:' + playpath[:-4]

        return (app_only_rtmpurl, playpath, ext)

    def rtmp_parameters_to_url(self, params):
        components = [params['rtmp']]
        for key, value in params.items():
            if key != 'rtmp':
                components.append('%s=%s' % (key, value))
        return ' '.join(components)

    def rtmp_parameters_to_rtmpdump_args(self, params):
        args = []
        for key, value in params.items():
            if key == 'live':
                args.append('--live')
            else:
                args.append('--%s=%s' % (key, value))
        return args


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
        return HLSBackend(self.hls_manifest_url, self.ext)

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


class KalturaLiveAudioStream(HTTPStream):
    def create_downloader(self):
        return HLSAudioBackend(self.url)


class SportsStream(HTTPStream):
    def create_downloader(self):
        return HLSBackend(self.url, '.mp4', long_probe=True)


class InvalidStream(AreenaStreamBase):
    def __init__(self, error_message):
        self.error = error_message


@attr.s
class PAPIStream(object):
    connect = attr.ib()
    stream = attr.ib()
