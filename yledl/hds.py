from __future__ import print_function, absolute_import, unicode_literals
import logging
import xml.dom
import base64
import miniamf

logger = logging.getLogger('yledl')


def parse_manifest(manifest):
    if not manifest:
        return []

    try:
        manifest_xml = xml.dom.minidom.parseString(manifest)
    except Exception:
        logger.exception('Failed to parse HDS manifest')
        return []

    medias = manifest_xml.getElementsByTagName('media')
    res = [_create_metadata_object(m) for m in medias]
    res = [x for x in res if x]
    return res


def parse_on_metadata_tag(tag_bytes):
    try:
        stream = miniamf.util.BufferedByteStream(tag_bytes)
        decoder = miniamf.get_decoder(miniamf.AMF0, stream)
        tag_name = decoder.readElement()
        if tag_name != 'onMetaData':
            return {}

        return decoder.readElement()
    except miniamf.BaseError:
        logger.exception('Failed to parse FLV metadata')
        return {}


def _parse_metadata_element(media_xml_element):
    for child in media_xml_element.childNodes:
        if child.nodeName == 'metadata' and child.hasChildNodes():
            decoded = base64.b64decode(child.firstChild.nodeValue)
            return parse_on_metadata_tag(decoded)
    return {}


def _create_metadata_object(media):
    res = {}
    other_metadata = _parse_metadata_element(media)
    _copy_optional_int_xml_attribute(media, res, 'bitrate')
    _copy_optional_string_xml_attribute(media, res, 'url', 'mediaurl')
    _copy_optional_int(other_metadata, res, 'width')
    _copy_optional_int(other_metadata, res, 'height')
    return res


def _copy_optional_string_xml_attribute(src_xml, dest, name, destname=None):
    value = src_xml.getAttribute(name)
    if value:
        dest[destname or name] = value


def _copy_optional_int_xml_attribute(src_xml, dest, name, destname=None):
    value = src_xml.getAttribute(name)
    if value:
        try:
            dest[destname or name] = int(value)
        except ValueError:
            pass


def _copy_optional_int(src, dest, name, destname=None):
    if name in src:
        try:
            dest[destname or name] = int(src.get(name))
        except ValueError:
            pass
