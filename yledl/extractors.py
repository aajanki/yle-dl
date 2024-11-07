# This file is part of yle-dl.
#
# Copyright 2010-2024 Antti Ajanki and others
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

import json
import logging
import re
from .areena_extractors import (AreenaExtractor, AreenaLiveRadioExtractor,
                                    AreenaLiveTVExtractor, AreenaPlaylistParser)
from .data_extractors import Clip

from .streamflavor import failed_flavor


logger = logging.getLogger('yledl')


def extractor_factory(url, language_chooser, httpclient, title_formatter, ffprobe):
    if (
        re.match(r'^https?://yle\.fi/aihe/', url)
        or re.match(r'^https?://svenska\.yle\.fi/artikel/', url)
        or re.match(r'^https?://svenska\.yle\.fi/a/', url)
    ):
        logger.debug(f'{url} is an Elävä Arkisto URL')
        return ElavaArkistoExtractor(
            language_chooser, httpclient, title_formatter, ffprobe
        )
    elif (
        re.match(r'^https?://areena\.yle\.fi/audio/ohjelmat/[-a-zA-Z0-9]+', url)
        or re.match(r'^https?://areena\.yle\.fi/podcastit/ohjelmat/[-a-zA-Z0-9]+', url)
        or re.match(r'^https?://areena\.yle\.fi/radio/suorat/[-a-zA-Z0-9]+', url)
    ):
        logger.debug(f'{url} is a live radio URL')
        return AreenaLiveRadioExtractor(
            language_chooser, httpclient, title_formatter, ffprobe
        )
    elif re.match(r'^https?://yle\.fi/(a|uutiset|urheilu|saa)/', url):
        logger.debug(f'{url} is a news URL')
        return YleUutisetExtractor(
            language_chooser, httpclient, title_formatter, ffprobe
        )
    elif re.match(r'^https?://(areena|arenan)\.yle\.fi/', url) or re.match(
        r'^https?://yle\.fi/', url
    ):
        logger.debug(f'{url} is an Areena URL')
        return AreenaExtractor(language_chooser, httpclient, title_formatter, ffprobe)
    elif url.lower() in ['tv1', 'tv2', 'teema']:
        logger.debug(f'{url} is a live TV channel')
        return AreenaLiveTVExtractor(
            language_chooser, httpclient, title_formatter, ffprobe
        )
    else:
        logger.debug(f'{url} is an unrecognized URL')
        return None


## Flavors


class Flavors:
    @staticmethod
    def media_type(media):
        mtype = media.get('type')
        if mtype == 'AudioObject' or (
            mtype is None and media.get('containerFormat') == 'mpeg audio'
        ):
            return 'audio'
        else:
            return 'video'



class FailedClip(Clip):
    def __init__(self, webpage, error_message, **kwargs):
        super().__init__(
            webpage=webpage, flavors=[failed_flavor(error_message)], **kwargs
        )


### Elava Arkisto ###


class ElavaArkistoExtractor(AreenaExtractor):
    def get_playlist(self, url, latest_only=False):
        ids = self.get_dataids(url)

        if latest_only:
            ids = ids[-1:]

        if ids:
            return [f'https://areena.yle.fi/{x}' for x in ids]
        else:
            # Fallback to Yle news parser because sometimes Elävä
            # arkisto pages are published using the same article type
            # as news articles.
            return parse_playlist_from_yle_article(url, self.httpclient, latest_only)

    def get_dataids(self, url):
        tree = self.httpclient.download_html_tree(url)
        if tree is None:
            return []

        return self.ordered_union(self._simple_dataids(tree), self._ydd_dataids(tree))

    def ordered_union(self, xs, ys):
        union = list(xs)  # copy
        for y in ys:
            if y not in union:
                union.append(y)
        return union

    def _simple_dataids(self, tree):
        dataids = tree.xpath("//article[@id='main-content']//div/@data-id")
        dataids = [str(d) for d in dataids]
        return [d if '-' in d else f'1-{d}' for d in dataids]

    def _ydd_dataids(self, tree):
        player_props = [
            json.loads(p)
            for p in tree.xpath("//main[@id='main-content']//div/@data-player-props")
        ]
        return [x['id'] for x in player_props if 'id' in x]


### News clips at the Yle news site ###


class YleUutisetExtractor(AreenaExtractor):
    def get_playlist(self, url, latest_only=False):
        return parse_playlist_from_yle_article(url, self.httpclient, latest_only)


def parse_playlist_from_yle_article(url, httpclient, latest_only):
    def id_to_areena_url(data_id):
        if '-' in data_id:
            areena_id = data_id
        else:
            areena_id = f'1-{data_id}'
        return f'https://areena.yle.fi/{areena_id}'

    tree = httpclient.download_html_tree(url)
    if tree is None:
        return []

    state = None
    state_script_nodes = tree.xpath(
        '//script[@type="text/javascript" and '
        '(contains(text(), "window.__INITIAL__STATE__") or '
        ' contains(text(), "window.__INITIAL_STATE__"))]/text()'
    )
    if len(state_script_nodes) > 0:
        state_json = re.sub(
            r'^window\.__INITIAL__?STATE__\s*=\s*', '', state_script_nodes[0]
        )
        state = json.loads(state_json)

    if state is None:
        state_div_nodes = tree.xpath('//div[@id="initialState"]')
        if len(state_div_nodes) > 0:
            state = json.loads(state_div_nodes[0].attrib.get('data-state'))

    if state is None:
        return []

    data_ids = []
    article = state.get('pageData', {}).get('article', {})
    if article.get('mainMedia') is not None:
        medias = article['mainMedia']
        data_ids = [
            media['id']
            for media in medias
            if media.get('type') in ['VideoBlock', 'video'] and 'id' in media
        ]
    else:
        headline_video_id = article.get('headline', {}).get('video', {}).get('id')
        if headline_video_id:
            data_ids = [headline_video_id]

    content = article.get('content', [])
    inline_media = [
        block['id']
        for block in content
        if block.get('type') in ['AudioBlock', 'audio', 'VideoBlock', 'video']
        and 'id' in block
    ]
    for id in inline_media:
        if id not in data_ids:
            data_ids.append(id)

    logger.debug(f"Found Areena data IDs: {','.join(data_ids)}")

    playlist = [id_to_areena_url(id) for id in data_ids]
    if latest_only:
        playlist = playlist[-1:]

    return playlist
