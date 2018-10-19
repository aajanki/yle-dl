# -*- coding: utf-8 -*-

from __future__ import print_function, absolute_import, unicode_literals
import attr
import logging
import os.path
import xml.dom.minidom


logger = logging.getLogger('yledl')


@attr.s
class PAPIStream(object):
    connect = attr.ib()
    stream = attr.ib()


def create_rtmp_params(streamurl, pageurl, httpclient):
    rtmp_stream = create_rtmpstream(streamurl)
    params = stream_to_rtmp_parameters(rtmp_stream, pageurl, False, httpclient)

    if params is not None:
        params['app'] = params['app'].split('/', 1)[0]

    return params


def create_rtmpstream(streamurl):
    (rtmpurl, playpath, ext) = parse_rtmp_single_component_app(streamurl)
    playpath = playpath.split('?', 1)[0]
    return PAPIStream(streamurl, playpath)


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


def stream_to_rtmp_parameters(stream, pageurl, islive, httpclient):
    if not stream:
        return None

    rtmp_connect = stream.connect
    rtmp_stream = stream.stream
    if not rtmp_stream:
        logger.error('No rtmp stream')
        return None

    try:
        scheme, edgefcs, rtmppath = rtmpurlparse(rtmp_connect)
    except ValueError:
        logger.exception('Failed to parse RTMP URL')
        return None

    ident = httpclient.download_page('http://%s/fcs/ident' % edgefcs)
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


def rtmpurlparse(url):
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


def rtmp_parameters_to_url(params):
    components = [params['rtmp']]
    for key, value in params.items():
        if key != 'rtmp':
            components.append('%s=%s' % (key, value))
    return ' '.join(components)


def rtmp_parameters_to_rtmpdump_args(params):
    if not params:
        return []

    args = []
    for key, value in params.items():
        if key == 'live':
            args.append('--live')
        else:
            args.append('--%s=%s' % (key, value))
    return args
