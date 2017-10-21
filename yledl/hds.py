import logging
import xml.dom
import base64
import pyamf

logger = logging.getLogger('yledl')


def parse_manifest(manifest):
    if not manifest:
        return []

    try:
        manifest_xml = xml.dom.minidom.parseString(manifest)
    except Exception:
        logger.exception('Failed to parse HDS manifest')
        return []

    res = []
    medias = manifest_xml.getElementsByTagName('media')
    for media in medias:
        bitrate = media.getAttribute('bitrate')
        metadata_dict = _parse_metadata_element(media)
        meta = _create_metadata_object(bitrate, metadata_dict)
        if meta:
            res.append(meta)

    return res


def bitrates_from_manifest(manifest):
    metadata = parse_manifest(manifest)
    return [m.get('bitrate') for m in metadata if m.get('bitrate', 0) > 0]


def parse_on_metadata_tag(tag_bytes):
    try:
        stream = pyamf.util.BufferedByteStream(tag_bytes)
        decoder = pyamf.get_decoder(pyamf.AMF0, stream)
        tag_name = decoder.readElement()
        if tag_name != 'onMetaData':
            return {}

        return decoder.readElement()
    except pyamf.BaseError:
        logger.exception('Failed to parse FLV metadata')
        return {}


def _parse_metadata_element(media_xml_element):
    for child in media_xml_element.childNodes:
        if child.nodeName == 'metadata' and child.hasChildNodes():
            decoded = base64.b64decode(child.firstChild.nodeValue)
            return parse_on_metadata_tag(decoded)
    return {}


def _create_metadata_object(bitrate, other_metadata):
    res = {}
    if bitrate:
        try:
            res['bitrate'] = int(bitrate)
        except ValueError:
            pass

    if 'width' in other_metadata:
        try:
            res['width'] = int(other_metadata['width'])
        except ValueError:
            pass

    if 'height' in other_metadata:
        try:
            res['height'] = int(other_metadata['height'])
        except ValueError:
            pass

    return res
