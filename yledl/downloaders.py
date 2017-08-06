# -*- coding: utf-8 -*-

from __future__ import print_function
import sys
import urllib
import urllib2
import re
import subprocess
import os
import os.path
import platform
import signal
import urlparse
import json
import xml.dom.minidom
import time
import codecs
import base64
import ctypes
import ctypes.util
import logging
import requests
from Crypto.Cipher import AES
from pkg_resources import resource_filename
from version import version
from utils import print_enc, progress_bar

# exit codes
RD_SUCCESS = 0
RD_FAILED = 1
RD_INCOMPLETE = 2


logger = logging.getLogger('yledl')


def downloader_factory(url, backends):
    if re.match(r'^https?://yle\.fi/aihe/', url) or \
            re.match(r'^https?://(areena|arenan)\.yle\.fi/26-', url):
        return RetryingDownloader(ElavaArkistoDownloader, backends)
    elif re.match(r'^https?://svenska\.yle\.fi/artikel/', url):
        return RetryingDownloader(ArkivetDownloader, backends)
    elif re.match(r'^https?://(www\.)?yle\.fi/radio/[a-zA-Z0-9/]+/suora', url):
        return RetryingDownloader(AreenaLiveRadioDownloader, backends)
    elif re.match(r'^https?://(areena|arenan)\.yle\.fi/tv/suorat/', url):
        return RetryingDownloader(Areena2014LiveDownloader, backends)
    elif re.match(r'^https?://yle\.fi/(uutiset|urheilu|saa)/', url):
        return RetryingDownloader(YleUutisetDownloader, backends)
    elif re.match(r'^https?://(areena|arenan)\.yle\.fi/', url) or \
            re.match(r'^https?://yle\.fi/', url):
        return RetryingDownloader(Areena2014Downloader, backends)
    else:
        return None


def download_page(url, extra_headers=None):
    """Returns contents of a HTML page at url."""
    if url.find('://') == -1:
        url = 'http://' + url
    if '#' in url:
        url = url[:url.find('#')]

    headers = yledl_headers()
    if extra_headers:
        headers.update(extra_headers)

    try:
        r = requests.get(url, headers=headers)
        r.raise_for_status()
    except requests.exceptions.RequestException:
        logger.exception(u"Can't read {}".format(url))
        return None

    metacharset = html_meta_charset(r.content)
    if metacharset:
        r.encoding = metacharset

    return r.text


def download_to_file(url, destination_filename, show_progress=False):
    enc = sys.getfilesystemencoding()
    encoded_filename = destination_filename.encode(enc, 'replace')
    with open(encoded_filename, 'w') as output:
        urlretrieve(url, output, show_progress)


def urlretrieve(url, destination, show_progress=False):
    r = requests.get(url, headers=yledl_headers(), stream=True)
    r.raise_for_status()

    with progress_bar(show_progress, r.headers) as progress:
        for chunk in r.iter_content(chunk_size=4196):
            destination.write(chunk)
            progress.next(len(chunk))


def yledl_headers():
    headers = requests.utils.default_headers()
    headers.update({'User-Agent': 'yle-dl/' + version.split(' ')[0]})
    return headers


def html_meta_charset(html_bytes):
    metacharset = re.search(r'<meta [^>]*?charset="(.*?)"', html_bytes)
    if metacharset:
        return metacharset.group(1)
    else:
        return None


def int_or_else(x, default):
    try:
        return int(x)
    except ValueError:
        return default


def parse_rtmp_single_component_app(rtmpurl):
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


def normalize_language_code(lang, subtype):
    if lang == 'all' or lang == 'none':
        return lang
    elif subtype == 'hearingimpaired':
        return lang + 'h'
    else:
        language_map = {'fi': 'fin', 'sv': 'swe'}
        return language_map.get(lang, lang)


class StreamFilters(object):
    """Parameters for deciding which of potentially multiple available stream
    versions to download.
    """
    def __init__(self, latest_only=False, audiolang='', sublang='all',
                 hardsubs=False, maxbitrate=sys.maxint, duration=None):
        self.latest_only = latest_only
        self.audiolang = audiolang
        self.sublang = sublang
        self.hardsubs = hardsubs
        self.maxbitrate = maxbitrate
        self.duration = duration

    def sublang_matches(self, langcode, subtype):
        return self._lang_matches(self.sublang, langcode, subtype)

    def audiolang_matches(self, langcode):
        return self.audiolang != '' and \
            self._lang_matches(self.audiolang, langcode, '')

    def _lang_matches(self, langA, langB, subtype):
        return normalize_language_code(langA, '') == \
          normalize_language_code(langB, subtype)


class IOContext(object):
    def __init__(self, outputfilename=None, destdir=None, resume=False,
                 ratelimit=None, excludechars='*/|', proxy=None,
                 rtmpdump_binary=None, hds_binary=None,
                 ffmpeg_binary='ffmpeg'):
        self.outputfilename = outputfilename
        self.destdir = destdir
        self.resume = resume
        self.ratelimit = ratelimit
        self.excludechars = excludechars
        self.proxy = proxy

        self.rtmpdump_binary = rtmpdump_binary
        self.ffmpeg_binary = ffmpeg_binary
        if hds_binary:
            self.hds_binary = hds_binary
        else:
            self.hds_binary = \
                ['php', resource_filename(__name__, 'AdobeHDS.php')]


class JSONP(object):
    @staticmethod
    def load_jsonp(url, headers=None):
        json_string = JSONP.remove_jsonp_padding(download_page(url, headers))
        if not json_string:
            return None

        try:
            json_parsed = json.loads(json_string)
        except ValueError:
            return None

        return json_parsed

    @staticmethod
    def remove_jsonp_padding(jsonp):
        if not jsonp:
            return None

        without_padding = re.sub(r'^[\w.]+\(|\);$', '', jsonp)
        if without_padding[:1] != '{' or without_padding[-1:] != '}':
            return None

        return without_padding


class BackendFactory(object):
    ADOBEHDSPHP = 'adobehdsphp'
    YOUTUBEDL = 'youtubedl'

    @staticmethod
    def is_valid_hds_backend(hds_backend):
        return (hds_backend == BackendFactory.ADOBEHDSPHP or
                hds_backend == BackendFactory.YOUTUBEDL)

    @staticmethod
    def parse_backends(backend_names):
        backends = []
        for bn in backend_names:
            if not BackendFactory.is_valid_hds_backend(bn):
                logger.warning(u'Invalid backend: ' + bn)
                continue

            backends.append(BackendFactory(bn))
        return backends

    def __init__(self, hds_backend):
        self.hds_backend = hds_backend

    def __str__(self):
        return 'HDS backend: %s' % self.hds_backend

    def hds(self):
        if self.hds_backend == self.YOUTUBEDL:
            return YoutubeDLHDSDump
        else:
            return HDSDump


# Areena

class AreenaUtils(object):
    def areena_decrypt(self, data, aes_key):
        try:
            bytestring = base64.b64decode(str(data))
        except (UnicodeEncodeError, TypeError):
            return None

        iv = bytestring[:16]
        ciphertext = bytestring[16:]
        padlen = 16 - (len(ciphertext) % 16)
        ciphertext = ciphertext + '\0'*padlen

        decrypter = AES.new(aes_key, AES.MODE_CFB, iv, segment_size=16*8)
        return decrypter.decrypt(ciphertext)[:-padlen]

    def download_subtitles(self, subtitles, filters, videofilename):
        subtitlefiles = []
        if not filters.hardsubs:
            preferred_lang = filters.sublang
            basename = os.path.splitext(videofilename)[0]
            for sub in subtitles:
                lang = sub.language
                if (filters.sublang_matches(lang, '') or
                        preferred_lang == 'all'):
                    if sub.url:
                        try:
                            filename = basename + '.' + lang + '.srt'
                            download_to_file(sub.url, filename)
                            self.add_BOM(filename)
                            logger.info(u'Subtitles saved to ' + filename)
                            subtitlefiles.append(filename)
                            if preferred_lang != 'all':
                                return subtitlefiles
                        except IOError:
                            logger.exception(u'Failed to download subtitles '
                                             u'at %s' % sub.url)
        return subtitlefiles

    def add_BOM(self, filename):
        """Add byte-order mark into a file.

        Assumes (but does not check!) that the file is UTF-8 encoded.
        """
        enc = sys.getfilesystemencoding()
        encoded_filename = filename.encode(enc, 'replace')

        with open(encoded_filename, 'r') as infile:
            content = infile.read()
            if content.startswith(codecs.BOM_UTF8):
                return

        with open(encoded_filename, 'w') as outfile:
            outfile.write(codecs.BOM_UTF8)
            outfile.write(content)


class KalturaUtils(object):
    def select_kaltura_stream(self, media_id, program_id, referer, filters):
        mw = self.load_mwembed(media_id, program_id, referer)
        return self.stream_from_mw(mw, filters)

    def load_mwembed(self, media_id, program_id, referer):
        entryid = self.kaltura_entry_id(media_id)
        mwembed_url = ('http://cdnapi.kaltura.com/html5/html5lib/v2.56/'
                       'mwEmbedFrame.php?&wid=_1955031&uiconf_id=32431531'
                       '&cache_st=1442926927&entry_id={entry_id}'
                       '&flashvars\[streamerType\]=auto'
                       '&flashvars\[EmbedPlayer.HidePosterOnStart\]=true'
                       '&flashvars\[EmbedPlayer.OverlayControls\]=true'
                       '&flashvars\[IframeCustomPluginCss1\]='
                       '%%2F%%2Fplayer.yle.fi%%2Fassets%%2Fcss%%2Fkaltura.css'
                       '&flashvars\[mediaProxy\]='
                       '%7B%22mediaPlayFrom%22%3Anull%7D'
                       '&flashvars\[autoPlay\]=true'
                       '&flashvars\[KalturaSupport.LeadWithHTML5\]=true'
                       '&flashvars\[loop\]=false'
                       '&flashvars\[sourceSelector\]='
                       '%7B%22hideSource%22%3Atrue%7D'
                       '&flashvars\[comScoreStreamingTag\]='
                       '%7B%22logUrl%22%3A%22%2F%2Fda.yle.fi%2Fyle%2Fareena%2Fs'
                       '%3Fname%3Dareena.kaltura.prod%22%2C%22plugin%22%3Atrue'
                       '%2C%22position%22%3A%22before%22%2C%22persistentLabels'
                       '%22%3A%22ns_st_mp%3Dareena.kaltura.prod%22%2C%22debug'
                       '%22%3Atrue%2C%22asyncInit%22%3Atrue%2C%22relativeTo%22'
                       '%3A%22video%22%2C%22trackEventMonitor%22%3A'
                       '%22trackEvent%22%7D'
                       '&flashvars\[closedCaptions\]='
                       '%7B%22hideWhenEmpty%22%3Atrue%7D'
                       '&flashvars\[Kaltura.LeadHLSOnAndroid\]=true'
                       '&playerId=kaltura-{program_id}-1&forceMobileHTML5=true'
                       '&urid=2.56'
                       '&protocol=http'
                       '&callback=mwi_kaltura1320086810'.format(
                           entry_id=urllib.quote_plus(entryid),
                           program_id=urllib.quote_plus(program_id)))
        mw = JSONP.load_jsonp(mwembed_url, {'Referer': referer})

        if mw:
            logger.debug('mwembed:')
            logger.debug(json.dumps(mw))

        return (mw or {}).get('content', '')

    def kaltura_entry_id(self, mediaid):
        return mediaid.split('-', 1)[-1]

    def stream_from_mw(self, mw, filters):
        package_data = self.package_data_from_mwembed(mw)
        flavors = (package_data
                   .get('entryResult', {})
                   .get('contextData', {})
                   .get('flavorAssets', []))
        meta = package_data.get('entryResult', {}).get('meta', {})

        web_flavors = [fl for fl in flavors if fl.get('isWeb', True)]
        num_non_web = len(flavors) - len(web_flavors)

        if num_non_web > 0:
            logger.debug(u'Ignored %d non-web flavors' % num_non_web)

        bitrates = [fl.get('bitrate', 0) for fl in web_flavors]
        logger.debug(u'Available bitrates: %s, maxbitrate = %s' %
                     (bitrates, filters.maxbitrate))

        return self.select_matching_stream(web_flavors, meta, filters)

    def select_matching_stream(self, flavors, meta, filters):
        # See http://cdnapi.kaltura.com/html5/html5lib/v2.56/load.php
        # for the actual Areena stream selection logic
        h264flavors = [f for f in flavors if self.is_h264_flavor(f)]
        if h264flavors:
            # Prefer non-adaptive HTTP stream
            stream_format = 'url'
            filtered_flavors = h264flavors
        elif meta.get('duration', 0) < 10:
            # short and durationless streams are not available as HLS
            stream_format = 'url'
            filtered_flavors = flavors
        else:
            # fallback to HLS if nothing else is available
            stream_format = 'applehttp'
            filtered_flavors = flavors

        return self.select_stream(filtered_flavors, stream_format, filters)

    def is_h264_flavor(self, flavor):
        tags = flavor.get('tags', '').split(',')
        ipad_h264 = 'ipad' in tags or 'iphone' in tags
        web_h264 = (('web' in tags or 'mbr' in tags) and
                    (flavor.get('fileExt') == 'mp4'))
        return ipad_h264 or web_h264

    def select_stream(self, flavors, stream_format, filters):
        selected_flavor = self.filter_flavors_by_bitrate(flavors, filters)
        if not selected_flavor:
            return InvalidStreamUrl('No admissible streams')
        if 'entryId' not in selected_flavor:
            return InvalidStreamUrl('No entryId in the selected flavor')

        entry_id = selected_flavor.get('entryId')
        flavor_id = selected_flavor.get('id', '0_00000000')
        ext = '.' + selected_flavor.get('fileExt', 'mp4')
        return self.stream_factory(
            entry_id, flavor_id, stream_format, filters, ext)

    def filter_flavors_by_bitrate(self, flavors, filters):
        valid_bitrates = [fl for fl in flavors
                          if fl.get('bitrate', 0) <= filters.maxbitrate]
        if not valid_bitrates and len(flavors) >= 1:
            valid_bitrates = [min(flavors,
                                  key=lambda fl: fl.get('bitrate', 0))]

        if not valid_bitrates:
            return {}

        selected = max(valid_bitrates, key=lambda fl: fl.get('bitrate', 0))
        logger.debug(u'Selected bitrate: %s' % selected.get('bitrate', 0))

        return selected

    def package_data_from_mwembed(self, mw):
        m = re.search('window.kalturaIframePackageData\s*=\s*', mw, re.DOTALL)
        if not m:
            return {}

        try:
            # The string contains extra stuff after the JSON object,
            # so let's use raw_decode()
            return json.JSONDecoder().raw_decode(mw[m.end():])[0]
        except ValueError:
            logger.error('Failed to parse kalturaIframePackageData!')
            return {}

    def stream_factory(self, entry_id, flavor_id, stream_format, filters, ext):
        if stream_format == 'applehttp':
            return KalturaHLSStreamUrl(entry_id, flavor_id, filters, ext)
        else:
            return KalturaHTTPStreamUrl(entry_id, flavor_id, stream_format, ext)


class KalturaStreamUtils(object):
    def manifest_url(self, entry_id, flavor_id, stream_format, manifest_ext):
        return ('http://cdnapi.kaltura.com/p/1955031/sp/195503100/'
                'playManifest/entryId/{entry_id}/flavorId/{flavor_id}/'
                'format/{stream_format}/protocol/http/a{ext}?'
                'referrer=aHR0cDovL2FyZW5hbi55bGUuZmk='
                '&playSessionId=11111111-1111-1111-1111-111111111111'
                '&clientTag=html5:v2.56&preferredBitrate=600'
                '&uiConfId=37558971'.format(
                    entry_id=entry_id,
                    flavor_id=flavor_id,
                    stream_format=stream_format,
                    ext=manifest_ext))


### Areena stream URL ###


class AreenaStreamBase(AreenaUtils):
    def __init__(self):
        self.error = None
        self.ext = '.flv'

    def is_valid(self):
        return not self.error

    def get_error_message(self):
        if self.is_valid():
            return None
        else:
            return self.error or 'Stream not valid'

    def to_url(self):
        return ''

    def to_rtmpdump_args(self):
        return None


class AreenaRTMPStreamUrl(AreenaStreamBase):
    # Extracted from
    # http://areena.yle.fi/static/player/1.2.8/flowplayer/flowplayer.commercial-3.2.7-encrypted.swf
    AES_KEY = 'hjsadf89hk123ghk'

    def __init__(self):
        AreenaStreamBase.__init__(self)
        self.rtmp_params = None

    def is_valid(self):
        return bool(self.rtmp_params)

    def to_url(self):
        return self.rtmp_parameters_to_url(self.rtmp_params)

    def to_rtmpdump_args(self):
        if self.rtmp_params:
            return self.rtmp_parameters_to_rtmpdump_args(self.rtmp_params)
        else:
            return []

    def create_downloader(self, io, clip_title):
        if not self.to_rtmpdump_args():
            return None
        else:
            return RTMPDump(self, clip_title, io)

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
        except ValueError as exc:
            logger.error(unicode(exc.message, 'utf-8', 'ignore'))
            return None

        ident = download_page('http://%s/fcs/ident' % edgefcs)
        if ident is None:
            logger.error('Failed to read ident')
            return None

        logger.debug(ident)

        try:
            identxml = xml.dom.minidom.parseString(ident)
        except Exception as exc:
            logger.error(unicode(exc.message, 'utf-8', 'ignore'))
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
            raise ValueError("Invalid RTMP URL")

        if '/' not in rest:
            raise ValueError("Invalid RTMP URL")

        server, app_and_playpath = rest.split('/', 1)
        return (scheme, server, app_and_playpath)

    def rtmp_parameters_to_url(self, params):
        components = [params['rtmp']]
        for key, value in params.iteritems():
            if key != 'rtmp':
                components.append('%s=%s' % (key, value))
        return ' '.join(components)

    def rtmp_parameters_to_rtmpdump_args(self, params):
        args = []
        for key, value in params.iteritems():
            if key == 'live':
                args.append('--live')
            else:
                args.append('--%s=%s' % (key, value))
        return args


class Areena2014HDSStreamUrl(AreenaStreamBase):
    def __init__(self, hdsurl, filters, backend):
        AreenaStreamBase.__init__(self)
        self.filters = filters
        self.downloader_class = backend.hds()

        if hdsurl:
            sep = '&' if '?' in hdsurl else '?'
            self.hds_url = hdsurl + sep + \
                'g=ABCDEFGHIJKL&hdcore=3.8.0&plugin=flowplayer-3.8.0.0'
        else:
            self.hds_url = None
        self.error = None

    def is_valid(self):
        return not self.error

    def get_error_message(self):
        if self.is_valid():
            return None
        else:
            return self.error or 'Stream not valid'

    def to_url(self):
        return self.hds_url

    def create_downloader(self, io, clip_title):
        return self.downloader_class(self, clip_title, io, self.filters)


class Areena2014RTMPStreamUrl(AreenaRTMPStreamUrl):
    def __init__(self, pageurl, streamurl, filters):
        AreenaRTMPStreamUrl.__init__(self)
        rtmpstream = self.create_rtmpstream(streamurl)
        self.rtmp_params = self.stream_to_rtmp_parameters(rtmpstream, pageurl,
                                                          False)
        self.rtmp_params['app'] = self.rtmp_params['app'].split('/', 1)[0]

    def create_rtmpstream(self, streamurl):
        (rtmpurl, playpath, ext) = parse_rtmp_single_component_app(streamurl)
        playpath = playpath.split('?', 1)[0]
        return PAPIStream(streamurl, playpath, 0, 0, False)


class HTTPStreamUrl(object):
    def __init__(self, url):
        self.url = url
        path = urlparse.urlparse(url)[2]
        self.ext = os.path.splitext(path)[1] or None

    def is_valid(self):
        return True

    def get_error_message(self):
        return None

    def to_url(self):
        return self.url

    def create_downloader(self, io, clip_title):
        return HTTPDump(self, clip_title, io)


class KalturaHLSStreamUrl(HTTPStreamUrl, KalturaStreamUtils):
    def __init__(self, entryid, flavorid, filters, ext='.mp4'):
        self.ext = ext
        self.url = self.manifest_url(entryid, flavorid, 'applehttp', '.m3u8')
        self.filters = filters

    def create_downloader(self, io, clip_title):
        return HLSDump(self, clip_title, io, self.filters)


class KalturaHTTPStreamUrl(HTTPStreamUrl, KalturaStreamUtils):
    def __init__(self, entryid, flavorid, stream_format, ext='.mp4'):
        self.ext = ext
        self.url = self.manifest_url(entryid, flavorid, stream_format, ext)


class InvalidStreamUrl(object):
    def __init__(self, error_message):
        self.error = error_message
        self.ext = None

    def is_valid(self):
        return False

    def get_error_message(self):
        return self.error

    def to_url(self):
        return ''


class PAPIStream(object):
    def __init__(self, connect, stream, videoBitrate, audioBitrate,
                 hardSubtitles):
        self.connect = connect
        self.stream = stream
        self.videoBitrate = int_or_else(videoBitrate, 0)
        self.audioBitrate = int_or_else(audioBitrate, 0)
        self.hardSubtitles = hardSubtitles

    def __str__(self):
        return json.dumps({
            'connect': self.connect,
            'stream': self.stream,
            'videoBitrate': self.videoBitrate,
            'audioBitrate': self.audioBitrate,
            'hardSubtitles': self.hardSubtitles})

    def bitrate(self):
        return self.videoBitrate + self.audioBitrate


### Areena (the new version with beta introduced in 2014) ###

class Areena2014Downloader(AreenaUtils, KalturaUtils):
    # Extracted from
    # http://player.yle.fi/assets/flowplayer-1.4.0.3/flowplayer/flowplayer.commercial-3.2.16-encrypted.swf
    AES_KEY = 'yjuap4n5ok9wzg43'

    def __init__(self, backend_factory):
        self.backend = backend_factory

    def download_episodes(self, url, io, filters, postprocess_command):
        def download_clip(clip):
            downloader = clip.streamurl.create_downloader(io, clip.title)
            if not downloader:
                logger.error(u'Downloading the stream at %s is not yet '
                             u'supported.' % url)
                logger.error(u'Try --showurl')
                return RD_FAILED

            outputfile = downloader.output_filename()
            subtitlefiles = \
                self.download_subtitles(clip.subtitles, filters, outputfile)
            dl_result = downloader.save_stream()
            if dl_result == RD_SUCCESS:
                self.postprocess(postprocess_command, outputfile,
                                 subtitlefiles)

            return dl_result

        return self.process(download_clip, url, filters)

    def print_urls(self, url, filters):
        def print_clip_url(clip):
            print_enc(clip.streamurl.to_url())
            return RD_SUCCESS

        return self.process(print_clip_url, url, filters)

    def print_episode_pages(self, url, filters):
        playlist = self.get_playlist(url, filters)
        for clipurl in playlist:
            print_enc(clipurl)

        return RD_SUCCESS

    def pipe(self, url, io, filters):
        def pipe_clip(clip):
            dl = clip.streamurl.create_downloader(io, clip.title)
            outputfile = dl.output_filename()
            self.download_subtitles(clip.subtitles, filters, outputfile)
            return dl.pipe()

        return self.process(pipe_clip, url, filters)

    def print_titles(self, url, filters):
        def print_clip_title(clip):
            print_enc(clip.title)
            return RD_SUCCESS

        return self.process(print_clip_title, url, filters)

    def process(self, clipfunc, url, filters):
        overall_status = RD_SUCCESS
        playlist = self.get_playlist(url, filters)
        for clipurl in playlist:
            res = self.process_single_episode(clipfunc, clipurl, filters)
            if res != RD_SUCCESS:
                overall_status = res
        return overall_status

    def get_playlist(self, url, filters):
        """If url is a series page, return a list of included episode pages."""
        playlist = []
        html = download_page(url)
        if html and self.is_playlist_page(html):
            series_id = self.program_id_from_url(url)
            playlist = self.playlist_episode_urls(series_id)

        if playlist is None:
            logger.error('Failed to parse a playlist')
            return []
        elif playlist:
            logger.debug('playlist page with %d clips' % len(playlist))
        else:
            logger.debug('not a playlist')
            playlist = [url]

        if filters.latest_only:
            playlist = playlist[:1]

        return playlist

    def playlist_episode_urls(self, series_id):
        # Areena server fails (502 Bad gateway) if page_size is larger
        # than 100.
        offset = 0
        page_size = 100
        playlist = []
        has_next_page = True
        while has_next_page:
            page = self.playlist_page(series_id, page_size, offset)
            if page is None:
                return None

            playlist.extend(page)
            offset += page_size
            has_next_page = len(page) == page_size
        return playlist

    def playlist_page(self, series_id, page_size, offset):
        logger.debug('Getting a playlist page {series_id}, '
                     'size = {size}, offset = {offset}'.format(
                         series_id=series_id, size=page_size, offset=offset))

        playlist_json = download_page(
            self.playlist_url(series_id, page_size, offset))
        if not playlist_json:
            return None

        try:
            playlist = json.loads(playlist_json)
        except ValueError:
            return None

        playlist_data = playlist.get('data', [])
        episode_ids = (x['id'] for x in playlist_data if 'id' in x)
        return ['https://areena.yle.fi/' + x for x in episode_ids]

    def playlist_url(self, series_id, page_size=100, offset=0):
        if offset:
            offset_param = '&offset={offset}'.format(offset=unicode(offset))
        else:
            offset_param = ''

        return ('https://areena.yle.fi/api/programs/v1/items.json?'
                'series={series_id}&type=program&availability=ondemand&'
                'order=episode.hash%3Adesc%2C'
                'publication.starttime%3Adesc%2Ctitle.fi%3Aasc&'
                'app_id=89868a18&app_key=54bb4ea4d92854a2a45e98f961f0d7da&'
                'limit={limit}{offset_param}'.format(
                    series_id=urllib.quote_plus(series_id),
                    limit=unicode(page_size),
                    offset_param=offset_param))

    def is_playlist_page(self, html):
        playlist_meta = '<meta property="og:type" content="video.tv_show">'
        player_class = 'class="yle_areena_player"'
        return playlist_meta in html or player_class not in html

    def process_single_episode(self, clipfunc, url, filters):
        clip = self.clip_for_url(url, filters)
        if clip.streamurl.is_valid():
            return clipfunc(clip)
        else:
            logger.error(u'Unsupported stream: %s' %
                         clip.streamurl.get_error_message())
            return RD_FAILED

    def clip_for_url(self, pageurl, filters):
        pid = self.program_id_from_url(pageurl)
        if not pid:
            return FailedClip(pageurl, 'Failed to parse a program ID')

        program_info = JSONP.load_jsonp(self.program_info_url(pid))
        if not program_info:
            return FailedClip(pageurl, 'Failed to download program data')

        logger.debug('program data:')
        logger.debug(json.dumps(program_info))

        unavailable = self.unavailable_clip(program_info, pageurl)
        return unavailable or \
            self.create_clip(program_info, pid, pageurl, filters)

    def unavailable_clip(self, program_info, pageurl):
        event = self.publish_event(program_info)
        expired_timestamp = self.event_expired_timestamp(event)
        if expired_timestamp:
            return FailedClip(pageurl, 'The clip has expired on %s' %
                              expired_timestamp)

        future_timestamp = self.event_in_future_timestamp(event)
        if future_timestamp:
            return FailedClip(pageurl, 'The clip will be published at %s' %
                              future_timestamp)

        return None

    def program_info_url(self, program_id):
        return 'http://player.yle.fi/api/v1/programs.jsonp?' \
            'id=%s&callback=yleEmbed.programJsonpCallback' % \
            (urllib.quote_plus(program_id))

    def create_clip(self, program_info, program_id, pageurl, filters):
        media_id = self.program_media_id(program_info, filters)
        if not media_id:
            return FailedClip(pageurl, 'Failed to parse media ID')

        if media_id.startswith('29-'):
            logger.debug('Detected an HTML5 video')

            streamurl = self.select_kaltura_stream(
                media_id, program_id, pageurl, filters)
            subtitle_media = self.select_yle_media(program_info, media_id,
                                                   program_id, 'HLS', filters)
            subtitles = self.media_subtitles(subtitle_media)
        else:
            selected_media = self.select_yle_media(program_info, media_id,
                                                   program_id, 'HDS', filters)
            if not selected_media:
                return FailedClip(pageurl, 'Media not found')

            streamurl = self.media_streamurl(selected_media, pageurl, filters)
            subtitles = self.media_subtitles(selected_media)

        return Clip(pageurl,
                    self.program_title(program_info),
                    streamurl,
                    subtitles)

    def select_yle_media(self, program_info, media_id, program_id,
                         default_video_proto, filters):
        proto = self.program_protocol(program_info, default_video_proto)
        medias = self.yle_media_descriptor(media_id, program_id, proto)
        if not medias:
            return {}

        return self.select_media(medias, filters)

    def yle_media_descriptor(self, media_id, program_id, protocol):
        media_jsonp_url = 'http://player.yle.fi/api/v1/media.jsonp?' \
                          'id=%s&callback=yleEmbed.startPlayerCallback&' \
                          'mediaId=%s&protocol=%s&client=areena-flash-player' \
                          '&instance=1' % \
            (urllib.quote_plus(media_id), urllib.quote_plus(program_id),
             urllib.quote_plus(protocol))
        media = JSONP.load_jsonp(media_jsonp_url)

        if media:
            logger.debug('media:')
            logger.debug(json.dumps(media))

        return media

    def program_id_from_url(self, url):
        parsed = urlparse.urlparse(url)
        return parsed.path.split('/')[-1]

    def program_media_id(self, program_info, filters):
        event = self.publish_event(program_info)
        return event.get('media', {}).get('id')

    def event_expired_timestamp(self, event):
        if event.get('temporalStatus') == 'in-past':
            return event.get('endTime')
        else:
            return None

    def event_in_future_timestamp(self, event):
        if event.get('temporalStatus') == 'in-future':
            return event.get('startTime')
        else:
            return None

    def program_title(self, program_info):
        program = program_info.get('data', {}).get('program', {})
        titleObject = program.get('title')
        title = self.fi_or_sv_text(titleObject) or 'areena'

        partOfSeasonObject = program.get('partOfSeason')

        if partOfSeasonObject:
            seasonNumberObject = partOfSeasonObject.get('seasonNumber')
        else:
            seasonNumberObject = program.get('seasonNumber')

        episodeNumberObject = program.get('episodeNumber')

        if seasonNumberObject and episodeNumberObject:
            title += ': S%02dE%02d' % (seasonNumberObject, episodeNumberObject)
        elif episodeNumberObject:
            title += ': E%02d' % (episodeNumberObject)

        itemTitleObject = program.get('itemTitle')
        itemTitle = self.fi_or_sv_text(itemTitleObject)

        promoTitleObject = program.get('promotionTitle')
        promotionTitle = self.fi_or_sv_text(promoTitleObject)

        if itemTitle and not title.endswith(itemTitle):
            title += ': ' + itemTitle
        elif promotionTitle and not promotionTitle.startswith(title):
            title += ': ' + promotionTitle

        date = self.publish_date(program_info)
        if date:
            title += '-' + date.replace('/', '-').replace(' ', '-')

        return title

    def program_protocol(self, program_info, default_video_proto):
        event = self.publish_event(program_info)
        if event.get('media', {}).get('type') == 'AudioObject':
            return 'RTMPE'
        else:
            return default_video_proto

    def publish_date(self, program_info):
        event = self.publish_event(program_info)
        return event.get('startTime')

    def publish_event(self, program_info):
        events = program_info.get('data', {}) \
                             .get('program', {}) \
                             .get('publicationEvent', [])

        has_current = any(self.publish_event_is_current(e) for e in events)
        if has_current:
            events = [e for e in events if self.publish_event_is_current(e)]

        with_media = [e for e in events if e.get('media')]
        if with_media:
            return with_media[0]
        else:
            return {}

    def publish_event_is_current(self, event):
        return event.get('temporalStatus') == 'currently'

    def localized_text(self, alternatives, language='fi'):
        if alternatives:
            return alternatives.get(language) or alternatives.get('fi')
        else:
            return None

    def fi_or_sv_text(self, alternatives):
        return self.localized_text(alternatives, 'fi') or \
            self.localized_text(alternatives, 'sv')

    def filter_by_subtitles(self, streams, filters):
        if filters.hardsubs:
            substreams = [s for s in streams if 'hardsubtitle' in s]
        else:
            substreams = [s for s in streams if 'hardsubtitle' not in s]

        if filters.sublang == 'all':
            filtered = substreams
        else:
            filtered = [s for s in substreams
                        if self.media_matches_sublang_filter(s, filters)]

        return filtered or streams

    def media_matches_sublang_filter(self, media, filters):
        if filters.hardsubs:
            subtitle = media.get('hardsubtitle', {})
            sublang = subtitle.get('lang', '')
            subtype = subtitle.get('type', '')
            return filters.sublang_matches(sublang, subtype)
        else:
            for subtitle in media.get('subtitles', []):
                sublang = subtitle.get('lang', '')
                subtype = subtitle.get('type', '')
                if filters.sublang_matches(sublang, subtype):
                    return True
            return False

    def select_media(self, media,  filters):
        protocol = media.get('meta', {}).get('protocol') or 'HDS'
        mediaobj = media.get('data', {}).get('media', {}).get(protocol, [])
        medias = self.filter_by_subtitles(mediaobj, filters)

        if medias:
            return medias[0]
        else:
            return {}

    def media_streamurl(self, media, pageurl, filters):
        url = media.get('url')
        if not url:
            return InvalidStreamUrl('No media URL')

        decodedurl = self.areena_decrypt(url, self.AES_KEY)
        if not decodedurl:
            return InvalidStreamUrl('Decrypting media URL failed')

        if media.get('protocol') == 'HDS':
            return Areena2014HDSStreamUrl(decodedurl, filters, self.backend)
        else:
            return Areena2014RTMPStreamUrl(pageurl, decodedurl, filters)

    def media_subtitles(self, media):
        subtitles = []
        for s in media.get('subtitles', []):
            uri = s.get('uri')
            lang = self.language_code_from_subtitle_uri(uri) or \
                normalize_language_code(s.get('lang'), s.get('type'))
            if uri:
                subtitles.append(Subtitle(uri, lang))
        return subtitles

    def language_code_from_subtitle_uri(self, uri):
        if uri.endswith('.srt'):
            ext = uri[:-4].rsplit('.', 1)[-1]
            if len(ext) <= 3:
                return ext
            else:
                return None
        else:
            return None

    def postprocess(self, postprocess_command, videofile, subtitlefiles):
        if postprocess_command:
            args = [postprocess_command, videofile]
            args.extend(subtitlefiles)
            return Subprocess().execute(args)


class Areena2014LiveDownloader(Areena2014Downloader):
    def program_info_url(self, program_id):
        quoted_pid = urllib.quote_plus(program_id)
        return 'http://player.yle.fi/api/v1/services.jsonp?' \
            'id=%s&callback=yleEmbed.simulcastJsonpCallback&' \
            'region=fi&instance=1&dataId=%s' % \
            (quoted_pid, quoted_pid)

    def program_media_id(self, program_info, filters):
        key_func = self.create_outlet_sort_key(filters)
        outlets = program_info.get('data', {}).get('outlets', [{}])
        sorted_outlets = sorted(outlets, key=key_func)
        selected_outlet = sorted_outlets[0]
        return selected_outlet.get('outlet', {}).get('media', {}).get('id')

    def create_outlet_sort_key(self, filters):
        preferred_ordering = {"fi": 1, None: 2, "sv": 3}

        def key_func(outlet):
            language = outlet.get("outlet", {}).get("language", [None])[0]
            if filters.audiolang_matches(language):
                return 0  # Prefer the language selected by the user
            else:
                return preferred_ordering.get(language) or 99

        return key_func

    def program_title(self, program_info):
        service = program_info.get('data', {}).get('service', {})
        title = self.fi_or_sv_text(service.get('title')) or 'areena'
        title += time.strftime('-%Y-%m-%d-%H:%M:%S')
        return title


class YleUutisetDownloader(Areena2014Downloader):
    def download_episodes(self, url, io, filters, postprocess_command):
        return self.delegate_to_areena_downloader(
            'download_episodes', url, io=io, filters=filters,
            postprocess_command=postprocess_command)

    def print_urls(self, url, filters):
        return self.delegate_to_areena_downloader(
            'print_urls', url, filters=filters)

    def print_episode_pages(self, url, filters):
        return self.delegate_to_areena_downloader(
            'print_episode_pages', url, filters=filters)

    def pipe(self, url, io, filters):
        return self.delegate_to_areena_downloader(
            'pipe', url, io, filters=filters)

    def print_titles(self, url, filters):
        return self.delegate_to_areena_downloader(
            'print_titles', url, filters=filters)

    def delegate_to_areena_downloader(self, method_name, url, *args, **kwargs):
        areena_urls = self.build_areena_urls(url)
        if areena_urls:
            logger.debug(u'Found areena URLs: ' + ', '.join(areena_urls))

            overall_status = RD_SUCCESS
            for url in areena_urls:
                kwcopy = dict(kwargs)
                kwcopy['url'] = url
                method = getattr(super(YleUutisetDownloader, self),
                                 method_name)
                res = method(*args, **kwcopy)
                if res != RD_SUCCESS:
                    overall_status = res

            return overall_status
        else:
            logger.error(u'No video stream found at ' + url)
            return RD_FAILED

    def build_areena_urls(self, url):
        html = download_page(url)
        if not html:
            return None

        player_re = r'<div[^>]*class="[^>]*yle_areena_player[^>]*data-id="([0-9-]+)"[^>]*>'
        dataids = re.findall(player_re, html, re.DOTALL)
        return [self.id_to_areena_url(id) for id in dataids]

    def id_to_areena_url(self, data_id):
        if '-' in data_id:
            areena_id = data_id
        else:
            areena_id = '1-' + data_id
        return 'https://areena.yle.fi/' + areena_id


class Clip(object):
    def __init__(self, pageurl, title, streamurl, subtitles):
        self.pageurl = pageurl
        self.title = title
        self.streamurl = streamurl
        self.subtitles = subtitles


class FailedClip(Clip):
    def __init__(self, pageurl, errormessage):
        Clip.__init__(self, pageurl, None, InvalidStreamUrl(errormessage),
                      None)


class Subtitle(object):
    def __init__(self, url, language):
        self.url = url
        self.language = language


### Areena live radio ###


class AreenaLiveRadioDownloader(Areena2014LiveDownloader):
    def get_playlist(self, url, filters):
        return [url]

    def program_id_from_url(self, pageurl):
        html = download_page(pageurl)
        if not html:
            return None

        stream_id = re.search(r"channelAreenaStreamId: *'(.*?)'", html)
        return stream_id.group(1) if stream_id else None


### Elava Arkisto ###


class ElavaArkistoDownloader(Areena2014Downloader):
    def get_playlist(self, url, filters):
        page = download_page(url)
        ids = re.findall(r' data-id="((?:1-|26-)[0-9]+)"', page or '')

        # TODO: The 26- IDs will point to non-existing pages. This
        # only shows up on --showepisodepage, everything else works.
        return ['https://areena.yle.fi/' + x for x in ids]

    def program_info_url(self, program_id):
        if program_id.startswith('26-'):
            did = program_id.split('-')[-1]
            return ('http://yle.fi/elavaarkisto/embed/%s.jsonp'
                    '?callback=yleEmbed.eaJsonpCallback'
                    '&instance=1&id=%s&lang=fi' %
                    (urllib.quote_plus(did), urllib.quote_plus(did)))
        else:
            return super(ElavaArkistoDownloader, self).program_info_url(
                program_id)

    def create_clip(self, program_info, program_id, pageurl, filters):
        download_url = program_info.get('downloadUrl')
        if download_url:
            title = self.program_title(program_info)
            return Clip(pageurl, title, HTTPStreamUrl(download_url), [])
        else:
            return super(ElavaArkistoDownloader, self).create_clip(
                program_info, program_id, pageurl, filters)

    def program_media_id(self, program_info, filters):
        mediakanta_id = program_info.get('mediakantaId')
        if mediakanta_id:
            return '6-' + mediakanta_id
        else:
            return super(ElavaArkistoDownloader, self).program_media_id(
                program_info, filters)

    def program_title(self, program_info):
        return program_info.get('title') or \
            program_info.get('originalTitle') or \
            super(ElavaArkistoDownloader, self).program_title(program_info) or \
            'elavaarkisto'


### Svenska Arkivet ###


class ArkivetDownloader(Areena2014Downloader):
    def get_playlist(self, url, filters):
        # The note about '26-' in ElavaArkistoDownloader applies here
        # as well
        ids = self.get_dataids(url)
        return ['https://areena.yle.fi/' + x for x in ids]

    def program_info_url(self, program_id):
        if program_id.startswith('26-'):
            plain_id = program_id.split('-')[-1]
            return 'https://player.yle.fi/api/v1/arkivet.jsonp?' \
                'id=%s&callback=yleEmbed.eaJsonpCallback&instance=1&lang=sv' % \
                (urllib.quote_plus(plain_id))
        else:
            return super(ArkivetDownloader, self).program_info_url(program_id)

    def program_media_id(self, program_info, filters):
        mediakanta_id = program_info.get('data', {}) \
                                    .get('ea', {}) \
                                    .get('mediakantaId')
        if mediakanta_id:
            return "6-" + mediakanta_id
        else:
            return super(ArkivetDownloader, self).program_media_id(
                program_info, filters)

    def program_title(self, program_info):
        ea = program_info.get('data', {}).get('ea', {})
        return (ea.get('otsikko') or
                ea.get('title') or
                ea.get('originalTitle') or
                super(ArkivetDownloader, self).program_title(program_info) or
                'yle-arkivet')

    def get_dataids(self, url):
        page = download_page(url)
        if not page:
            return []

        dataids = re.findall(r' data-id="((?:1-|26-)?[0-9]+)"', page)
        dataids = [d if '-' in d else '1-' + d for d in dataids]
        return dataids


### Downloader wrapper class that retries using different backends ###
### until the download succeeds ###


class RetryingDownloader(object):
    def __init__(self, wrapped_class, backend_factories):
        self.wrapped_class = wrapped_class
        self.backends = list(backend_factories)

    def _create_next_downloader(self):
        if self.backends:
            backend = self.backends.pop(0)
            logger.debug(str(backend))
            return self.wrapped_class(backend)
        else:
            return None

    def _retry_call(self, method_name, *args, **kwargs):
        downloader = self._create_next_downloader()
        if not downloader:
            return RD_FAILED

        method = getattr(downloader, method_name)
        res = method(*args, **kwargs)
        if res == RD_FAILED:
            return self._retry_call(method_name, *args, **kwargs)
        else:
            return res

    def print_urls(self, *args, **kwargs):
        return self._retry_call('print_urls', *args, **kwargs)

    def print_episode_pages(self, *args, **kwargs):
        return self._retry_call('print_episode_pages', *args, **kwargs)

    def print_titles(self, *args, **kwargs):
        return self._retry_call('print_titles', *args, **kwargs)

    def download_episodes(self, *args, **kwargs):
        return self._retry_call('download_episodes', *args, **kwargs)

    def pipe(self, *args, **kwargs):
        return self._retry_call('pipe', *args, **kwargs)


### Download a stream to a local file ###


class BaseDownloader(object):
    def __init__(self, stream, clip_title, io):
        self.stream = stream
        self.clip_title = clip_title or 'ylestream'
        self.destdir = io.destdir or ''
        if io.outputfilename:
            self.preferred_name = self.append_ext_if_missing(
                io.outputfilename, self.stream.ext)
        else:
            self.preferred_name = None
        self._cached_output_file = None
        self.excludechars = io.excludechars
        self.resume = io.resume
        self.proxy = io.proxy

        if self.resume and not self.resume_supported():
            logger.warning('Resume not supported on this stream')

    def save_stream(self):
        """Deriving classes override this to perform the download"""
        raise NotImplementedError('save_stream must be overridden')

    def pipe(self):
        """Derived classes can override this to pipe to stdout"""
        return RD_FAILED

    def outputfile_from_clip_title(self, resume=False):
        if self._cached_output_file:
            return self._cached_output_file

        ext = self.stream.ext or '.flv'
        filename = self.sane_filename(self.clip_title, self.excludechars) + ext
        if self.destdir:
            filename = os.path.join(self.destdir, filename)
        if not resume:
            filename = self.next_available_filename(filename)
        self._cached_output_file = filename
        return filename

    def next_available_filename(self, proposed):
        i = 1
        enc = sys.getfilesystemencoding()
        filename = proposed
        basename, ext = os.path.splitext(filename)
        while os.path.exists(filename.encode(enc, 'replace')):
            logger.info(u'%s exists, trying an alternative name' % filename)
            filename = basename + '-' + str(i) + ext
            i += 1

        return filename

    def append_ext_if_missing(self, filename, default_ext):
        if '.' in filename:
            return filename
        else:
            return filename + (default_ext or '.flv')

    def log_output_file(self, outputfile, done=False):
        if outputfile and outputfile != '-':
            if done:
                logger.info(u'Stream saved to ' + outputfile)
            else:
                logger.info(u'Output file: ' + outputfile)

    def sane_filename(self, name, excludechars):
        if isinstance(name, str):
            name = unicode(name, 'utf-8', 'ignore')
        tr = dict((ord(c), ord(u'_')) for c in excludechars)
        x = name.strip(' .').translate(tr)
        return x or u'ylevideo'

    def output_filename(self):
        resume_job = self.resume and self.resume_supported()
        return (self.preferred_name or
                self.outputfile_from_clip_title(resume=resume_job))

    def resume_supported(self):
        return False


### Dumping a stream to a file using external programs ###


class ExternalDownloader(BaseDownloader):
    def save_stream(self):
        args = self.build_args()
        outputfile = self.output_filename()
        self.log_output_file(outputfile)
        retcode = self.external_downloader(args)
        if retcode == RD_SUCCESS:
            self.log_output_file(outputfile, True)
        return retcode

    def build_args(self):
        return []

    def external_downloader(self, args):
        return Subprocess().execute(args)


class Subprocess(object):
    def execute(self, args):
        """Start an external process such as rtmpdump with argument list args
        and wait until completion.
        """
        logger.debug('Executing:')
        logger.debug(' '.join(args))

        enc = sys.getfilesystemencoding()
        encoded_args = [x.encode(enc, 'replace') for x in args]

        try:
            if platform.system() == 'Windows':
                process = subprocess.Popen(encoded_args)
            else:
                process = subprocess.Popen(
                    encoded_args, preexec_fn=self._sigterm_when_parent_dies)
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
            logger.error(u'Failed to execute ' + ' '.join(args))
            logger.error(unicode(exc.strerror, 'UTF-8', 'replace'))
            return RD_FAILED

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


class RTMPDump(ExternalDownloader):
    def __init__(self, stream, clip_title, io):
        ExternalDownloader.__init__(self, stream, clip_title, io)
        self.rtmpdump_binary = io.rtmpdump_binary

    def resume_supported(self):
        return True

    def build_args(self):
        args = [self.rtmpdump_binary]
        args += self.stream.to_rtmpdump_args()
        args += ['-o', self.output_filename()]
        if self.resume:
            args.append('-e')
        return args

    def pipe(self):
        args = [self.rtmpdump_binary]
        args += self.stream.to_rtmpdump_args()
        args += ['-o', '-']
        self.external_downloader(args)
        return RD_SUCCESS


### Download a stream by delegating to AdobeHDS.php ###


class HDSDump(ExternalDownloader):
    def __init__(self, stream, clip_title, io, filters):
        ExternalDownloader.__init__(self, stream, clip_title, io)
        self.quality_options = self._filter_options(filters, io)
        self.hds_binary = io.hds_binary

    def resume_supported(self):
        return True

    def _filter_options(self, filters, io):
        options = []

        # Approximate because there is no easy way to find out the
        # available bitrates in the HDS stream
        if filters.maxbitrate < 1000:
            options.extend(['--quality', 'low'])
        elif filters.maxbitrate < 2000:
            options.extend(['--quality', 'medium'])

        if io.ratelimit:
            options.extend(['--maxspeed', str(io.ratelimit)])

        if filters.duration:
            options.extend(['--duration', str(filters.duration)])

        return options

    def build_args(self):
        return self.adobehds_command_line([
            '--delete',
            '--outfile', self.output_filename()])

    def pipe(self):
        args = self.adobehds_command_line(['--play'])
        self.external_downloader(args)
        self.cleanup_cookies()
        return RD_SUCCESS

    def adobehds_command_line(self, extra_args):
        args = list(self.hds_binary)
        args.append('--manifest')
        args.append(self.stream.to_url())
        args.extend(self.quality_options)
        if self.proxy:
            args.append('--proxy')
            args.append(self.proxy)
            args.append('--fproxy')
        if logger.isEnabledFor(logging.DEBUG):
            args.append('--debug')
        if extra_args:
            args.extend(extra_args)
        return args

    def cleanup_cookies(self):
        try:
            os.remove('Cookies.txt')
        except OSError:
            pass


### Download a stream delegating to the youtube_dl HDS downloader ###


class YoutubeDLHDSDump(BaseDownloader):
    def __init__(self, stream, clip_title, io, filters):
        BaseDownloader.__init__(self, stream, clip_title, io)
        self.maxbitrate = filters.maxbitrate
        self.ratelimit = io.ratelimit

        if filters.duration:
            logger.warning(u'--duration will be ignored when using the '
                           u'youtube-dl backend')

    def resume_supported(self):
        return True

    def save_stream(self):
        return self._execute_youtube_dl(self.output_filename())

    def pipe(self):
        return self._execute_youtube_dl(u'-')

    def _execute_youtube_dl(self, outputfile):
        try:
            import youtube_dl
        except ImportError:
            logger.error(u'Failed to import youtube_dl')
            return RD_FAILED

        if outputfile != '-':
            self.log_output_file(outputfile)

        ydlopts = {
            'logtostderr': True,
            'proxy': self.proxy,
            'verbose': logger.isEnabledFor(logging.DEBUG)
        }

        dlopts = {
            'nopart': True,
            'continuedl': outputfile != '-' and self.resume
        }
        dlopts.update(self._ratelimit_parameter())

        ydl = youtube_dl.YoutubeDL(ydlopts)
        f4mdl = youtube_dl.downloader.F4mFD(ydl, dlopts)
        info = {'url': self.stream.to_url()}
        info.update(self._bitrate_parameter())
        try:
            if not f4mdl.download(outputfile, info):
                return RD_FAILED
        except urllib2.HTTPError:
            logger.exception(u'HTTP request failed')
            return RD_FAILED

        if outputfile != '-':
            self.log_output_file(outputfile, True)
        return RD_SUCCESS

    def _stream_bitrates(self):
        manifest = download_page(self.stream.to_url())
        if not manifest:
            return []

        try:
            manifest_xml = xml.dom.minidom.parseString(manifest)
        except Exception as exc:
            logger.error(unicode(exc.message, 'utf-8', 'ignore'))
            return []

        medias = manifest_xml.getElementsByTagName('media')
        bitrates = (int_or_else(m.getAttribute('bitrate'), 0) for m in medias)
        return [br for br in bitrates if br > 0]

    def _bitrate_parameter(self):
        bitrates = self._stream_bitrates()
        logger.debug(u'Available bitrates: %s, maxbitrate = %s' %
                     (bitrates, self.maxbitrate))

        if not bitrates:
            return {}

        acceptable_bitrates = [br for br in bitrates if br <= self.maxbitrate]
        if not acceptable_bitrates:
            selected_bitrate = min(bitrates)
        else:
            selected_bitrate = max(acceptable_bitrates)

        logger.debug(u'Selected bitrate: %s' % selected_bitrate)

        return {'tbr': selected_bitrate}

    def _ratelimit_parameter(self):
        if self.ratelimit:
            return {'ratelimit': self.ratelimit*1024}
        else:
            return {}


### Download a HLS stream by delegating to ffmpeg ###


class HLSDump(ExternalDownloader):
    def __init__(self, stream, clip_title, io, filters):
        ExternalDownloader.__init__(self, stream, clip_title, io)
        self.duration_options = self._filter_options(filters)
        self.ffmpeg_binary = io.ffmpeg_binary

    def _filter_options(self, filters):
        if filters.duration:
            return ['-t', str(filters.duration)]
        else:
            return []

    def build_args(self):
        return self.ffmpeg_command_line(
            ['-bsf:a', 'aac_adtstoasc', 'file:' + self.output_filename()])

    def pipe(self):
        args = self.ffmpeg_command_line(['-f', 'mpegts', 'pipe:1'])
        self.external_downloader(args)
        return RD_SUCCESS

    def ffmpeg_command_line(self, output_options):
        debug = logger.isEnabledFor(logging.DEBUG)
        loglevel = 'info' if debug else 'error'
        args = [self.ffmpeg_binary, '-y',
                '-loglevel', loglevel, '-stats',
                '-i', self.stream.to_url(),
                '-vcodec', 'copy', '-acodec', 'copy']
        args.extend(self.duration_options)
        args.extend(output_options)
        return args


### Download a plain HTTP file ###


class HTTPDump(BaseDownloader):
    def save_stream(self):
        logger.debug('Downloading from HTTP server...')
        logger.debug('URL: %s' % self.stream.to_url())
        filename = self.output_filename()
        self.log_output_file(filename)

        try:
            download_to_file(self.stream.to_url(), filename, show_progress=True)
        except IOError as exc:
            logger.error(u'Download failed: ' +
                         unicode(exc.message, 'UTF-8', 'replace'))
            return RD_FAILED

        self.log_output_file(filename, True)
        return RD_SUCCESS

    def pipe(self):
        url = self.stream.to_url()
        logger.debug('URL: %s' % url)

        try:
            urlretrieve(url, sys.stdout)
            sys.stdout.flush()
        except requests.exceptions.RequestException:
            logger.exception(u"Can't read {}".format(url))
            return RD_FAILED

        return RD_SUCCESS
