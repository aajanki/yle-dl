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

import attr
import logging
import json
import base64
from .backends import DASHHLSBackend, HLSAudioBackend, WgetBackend
from .streamflavor import StreamFlavor, FailedFlavor
from .subtitles import EmbeddedSubtitle


logger = logging.getLogger('yledl')


class KalturaApiClient:
    def __init__(self, api_url, httpclient):
        self.api_url = api_url
        self.httpclient = httpclient

    def start_widget_session(self, widget_id):
        return {
            'service': 'session',
            'action': 'startWidgetSession',
            'widgetId': widget_id
        }

    def list_base_entry(self, entry_id, ks):
        return {
            'service': 'baseEntry',
            'action': 'list',
            'ks': ks,
            'filter': {
                'redirectFromEntryId': entry_id
            },
            'responseProfile': {
                'fields': ('id,name,description,thumbnailUrl,dataUrl,duration,'
                           'msDuration,flavorParamsIds,mediaType,type,tags,'
                           'dvrStatus'),
                'type': 1
            }
        }

    def list_metadata(self, entry_id, ks):
        return {
            'service': 'metadata_metadata',
            'action': 'list',
            'filter': {
                'objectType': 'KalturaMetadataFilter',
                'objectIdEqual': entry_id,
                'metadataObjectTypeEqual': '1'
            },
            'ks': ks
        }

    def get_playback_context(self, entry_id, ks):
        return {
            'service': 'baseEntry',
            'action': 'getPlaybackContext',
            'entryId': entry_id,
            'ks': ks,
            'contextDataParams': {
                'objectType': 'KalturaContextDataParams',
                'flavorTags': 'all'
            }
        }

    def multi_request(self, subrequests, client_tag, partner_id):
        mrequest = {
            'apiVersion': '3.3.0',
            'format': 1,
            'ks': '',
            'clientTag': client_tag,
            'partnerId': partner_id
        }
        mrequest.update({str(i + 1): req for i, req in enumerate(subrequests)})
        return mrequest

    def perform_request(self, request, referrer, origin):
        endpoint = f'{self.api_url}/api_v3/service/multirequest'
        extra_headers = {
            'Referer': referrer,
            'Origin': origin,
            'Cache-Control': 'max-age=0'
        }
        r = self.httpclient.post(endpoint, request, extra_headers)
        return r.json()


class YleKalturaApiClient(KalturaApiClient):
    partner_id = '1955031'
    widget_id = '_1955031'
    client_tag = 'html5:v1.7.1'
    api_url = 'https://cdnapisec.kaltura.com'
    http_origin = 'https://areena.yle.fi'

    def __init__(self, requests_session):
        super().__init__(self.api_url, requests_session)

    def playback_context(self, entry_id, referrer):
        subrequests = [
            self.start_widget_session(self.widget_id),
            self.list_base_entry(entry_id, '{1:result:ks}'),
            self.get_playback_context('{2:result:objects:0:id}', '{1:result:ks}'),
            self.list_metadata('{2:result:objects:0:id}', '{1:result:ks}')
        ]
        mreq = self.multi_request(subrequests, self.client_tag, self.partner_id)

        logger.debug('Sending Kaltura API flavors request:\n' +
                     json.dumps(mreq, indent=2))

        response = self.perform_request(mreq, referrer, self.http_origin)

        logger.debug('Kaltura API response:\n' +
                     json.dumps(response, indent=2))

        return response[2] if len(response) > 2 else None

    def parse_stream_flavors(self, playback_context, referrer):
        if playback_context is None:
            return [FailedFlavor('No Kaltura playback context')]

        flavor_assets = playback_context.get('flavorAssets', {})
        sources = playback_context.get('sources', [])
        delivery_profiles = self.delivery_profiles_by_flavor_id(sources)

        filtered_flavors = [fl for fl in flavor_assets
                            if self.is_web_stream(fl)]
        num_non_web = len(flavor_assets) - len(filtered_flavors)
        if num_non_web:
            logger.debug(f'Ignored {num_non_web:d} non-web flavors')

        return self.create_flavors(filtered_flavors, delivery_profiles, referrer)

    def parse_embedded_subtitles(self, playback_context):
        language_name_to_code = {
            'finnish': 'fin',
            'swedish': 'swe'
        }

        categories = {
            'översättning': 'käännöstekstitys',
            'programtextning': 'ohjelmatekstitys'
        }

        subtitles = []
        for caption in playback_context.get('playbackCaptions', []):
            language_name = caption.get('language', '').lower()
            language_code = language_name_to_code.get(language_name, 'unk')
            label = caption.get('label')
            category = categories.get(label, label)
            subtitles.append(EmbeddedSubtitle(language_code, category))

        return subtitles

    def create_flavors(self, flavors, delivery_profiles, referrer):
        res = []
        for flavor in flavors:
            flavor_id = flavor.get('id')
            entry_id = flavor.get('entryId')
            ext = '.' + flavor.get('fileExt', 'mp4')
            media_type = self.flavor_media_type(flavor)
            is_live = flavor.get('objectType') == 'KalturaLiveAsset'

            backends = []
            for profile in delivery_profiles.get(flavor_id, []):
                backends.extend(profile.backends(
                    entry_id, media_type, is_live, ext, self.partner_id,
                    self.client_tag, referrer))

            res.append(StreamFlavor(
                media_type=media_type,
                height=flavor.get('height') or None,
                width=flavor.get('width') or None,
                bitrate=flavor.get('bitrate'),
                streams=backends
            ))

        return res

    def flavor_media_type(self, flavor):
        audio_stream = ('audio_only' in self.flavor_tags(flavor) or
                        flavor.get('containerFormat') == 'mpeg audio')
        return 'audio' if audio_stream else 'video'

    def flavor_tags(self, flavor):
        tags_string = flavor.get('tags')
        return tags_string.split(',') if tags_string else []

    def is_web_stream(self, flavor):
        tags = self.flavor_tags(flavor)
        web = 'web' in tags and 'source' not in tags
        mbr = 'mbr' in tags and flavor.get('fileExt') == 'mp4'
        ipad = 'ipad' in tags or 'iphone' in tags
        return web or mbr or ipad

    def delivery_profiles_by_flavor_id(self, sources):
        profiles = {}
        for source in sources:
            flavor_ids = source.get('flavorIds', '').split(',')
            source_format = source.get('format')
            manifest_file = source.get('url').split('/')[-1]

            for flavor_id in flavor_ids:
                p = DeliveryProfile(
                    flavor_id,
                    source_format,
                    manifest_file,
                )
                profiles.setdefault(p.flavor_id, set()).add(p)

        # Filter profiles: Take HLS and URL profiles when available. Ignore
        # other stream types.
        profiles_filtered = {}
        for flavor_id, profiles_for_flavor in profiles.items():
            hls_profiles = [p for p in profiles_for_flavor if p.stream_format == 'applehttp']
            url_profiles = [p for p in profiles_for_flavor if p.stream_format == 'url']
            profiles_filtered[flavor_id] = hls_profiles + url_profiles

        return profiles_filtered


@attr.frozen
class DeliveryProfile:
    flavor_id: str
    stream_format: str
    manifest_file: str

    def manifest_url(self, entry_id, partner_id, client_tag, referrer):
        b64referrer = base64.b64encode(referrer.encode('utf-8')).decode('utf-8')
        return (
            f'https://cdnsecakmi.kaltura.com/p/{partner_id}/'
            f'sp/{partner_id}00/playManifest/entryId/{entry_id}/'
            f'flavorId/{self.flavor_id}/format/{self.stream_format}/protocol/https/'
            f'{self.manifest_file}?uiConfId=43362851&referrer={b64referrer}'
            f'&playSessionId=11111111-1111-1111-1111-111111111111&clientTag={client_tag}'
        )

    def backends(self, entry_id, media_type, is_live, file_ext, partner_id, client_tag, referrer):
        backends = []
        manifest_url = self.manifest_url(entry_id, partner_id,
                                         client_tag, referrer)

        if media_type == 'audio':
            backends.extend([
                HLSAudioBackend(manifest_url),
                WgetBackend(manifest_url, file_ext)
            ])
        elif self.stream_format == 'url':
            backends.append(WgetBackend(manifest_url, file_ext))
        elif self.stream_format == 'applehttp':
            backends.append(DASHHLSBackend(
                manifest_url, is_live=is_live, experimental_subtitles=True))
        else:  # DASH
            backends.append(DASHHLSBackend(manifest_url, is_live=is_live))

        return backends
