from datetime import datetime
import json
from typing import List

import logging
from .data_extractors import EpisodeMetadata
from .http import update_url_query
from .play_list_data import PlaylistData
from .timestamp import parse_areena_timestamp

logger = logging.getLogger('yledl')

class AreenaPlaylistParser:
    """Get a list of episodes in a series from Areena API

    Reference: https://docs.api.yle.fi/api/programs-api-v3
    """

    def __init__(self, httpclient):
        self.httpclient = httpclient

    def get(self, url, latest_only=False):
        """If url is a series page, return a list of included episode pages."""
        tree = self.httpclient.download_html_tree(url)
        if tree is None:
            logger.warning(f'Failed to download {url} while looking for a playlist')
            return [url]

        playlist = []
        playlist_data = None
        if self._is_tv_series_page(tree):
            logger.debug('TV playlist')
            playlist_data = self._parse_series_playlist(tree)
        elif self._is_radio_series_page(tree):
            logger.debug('Radio playlist')
            playlist_data = self._parse_radio_playlist(tree)
        elif self._extract_package_id(tree) is not None:
            logger.debug('Package playlist')
            playlist_data = self._parse_package_playlist(tree)
        else:
            logger.debug('Not a playlist')
            playlist = [url]

        if playlist_data is not None:
            playlist = self._download_playlist_or_latest(playlist_data, latest_only)
            logger.debug(f'playlist page with {len(playlist)} episodes')

        return playlist

    def _is_tv_series_page(self, tree):
        next_data_tag = tree.xpath('//script[@id="__NEXT_DATA__"]')
        if len(next_data_tag) == 0:
            return False

        next_data = json.loads(next_data_tag[0].text)
        ptype = (
            next_data.get('props', {})
            .get('pageProps', {})
            .get('meta', {})
            .get('item', {})
            .get('type')
        )

        return ptype in ['TVSeries', 'TVSeason', 'TVView', 'RadioSeries', 'Package']

    def _is_radio_series_page(self, tree):
        is_radio_page = len(tree.xpath('//div[contains(@class, "RadioPlayer")]')) > 0
        if is_radio_page:
            episode_modal = tree.xpath('//div[starts-with(@class, "EpisodeModal")]')
            play_button = tree.xpath(
                '//main//button[starts-with(@class, "PlayButton")]'
            )
            return not episode_modal and not play_button
        else:
            return False

    def _parse_series_playlist(self, html_tree):
        next_data_tag = html_tree.xpath('//script[@id="__NEXT_DATA__"]')
        if next_data_tag:
            next_data = json.loads(next_data_tag[0].text)
            page_props = next_data.get('props', {}).get('pageProps', {})
            tabs = page_props.get('view', {}).get('tabs', [])
            first_tab_slug = tabs[0].get('slug') if tabs else None
            selected_tab = page_props.get('selectedTab') or first_tab_slug or 'jaksot'
            return self._parse_episodes_tab(
                tabs, selected_tab
            ) or self._parse_episodes_tab(tabs, None)

        return None

    def _parse_episodes_tab(self, next_data_tabs, tab_slug):
        if tab_slug:
            episodes_tab = [
                tab for tab in next_data_tabs if tab.get('slug') == tab_slug
            ]
        else:
            episodes_tab = [
                tab
                for tab in next_data_tabs
                if tab.get('type') == 'tab' and 'title' not in tab
            ]

        if episodes_tab:
            episodes_content = episodes_tab[0].get('content', [])
            if episodes_content:
                playlist_data = episodes_content[0]
                if playlist_data.get('title') not in ['Katso myös', 'Kuuntele myös']:
                    uri = playlist_data.get('source', {}).get('uri')

                    series_parameters = {}
                    filters = playlist_data.get('filters', [])
                    if filters:
                        options = filters[0].get('options', [])
                        series_parameters = [x['parameters'] for x in options]

                    return PlaylistData(uri, series_parameters)

        return None

    def _parse_package_playlist(self, html_tree):
        package_tag = html_tree.xpath('//div[@class="package-view"]/@data-view')
        if package_tag:
            package_data = json.loads(package_tag[0])
            tabs = package_data.get('tabs', [])
            if tabs:
                content = tabs[0].get('content', [])
                if content:
                    uri = content[0].get('source', {}).get('uri')
                    return PlaylistData(uri, [])

        return None

    def _parse_radio_playlist(self, html_tree):
        state_tag = html_tree.xpath(
            '//script[contains(., "window.STORE_STATE_FROM_SERVER")]'
        )
        if state_tag:
            state_str = state_tag[0].text
            data = json.loads(state_str.split('=', 1)[-1].strip())
            tabs = data.get('viewStore', {}).get('viewPageView', {}).get('tabs', [])
            tabs = [t for t in tabs if t.get('title') in ['Jaksot', 'Avsnitt']]
            if tabs:
                all_content = tabs[0].get('allContent')
                if all_content:
                    uri = all_content[0].get('source', {}).get('uri')
                    return PlaylistData(uri, [])

        return None

    def _download_playlist_or_latest(self, playlist_data, latest_only):
        season_urls = list(enumerate(playlist_data.season_playlist_urls(), start=1))
        if latest_only:
            # Optimization: The latest episode belongs to the latest season
            season_urls = season_urls[-1:]

        playlist = self._download_playlist(season_urls)

        # Heuristics: If most episodes do not have an episode number,
        # use time-based sorting.
        if self._episode_numbers_are_rare(playlist) and self._timestamps_are_common(
            playlist
        ):
            playlist = [x.with_episode_number(None) for x in playlist]

        # We can't control whether Areena API returns episodes in
        # ascending or descending order. Additionally, metadata
        # contains only the date (not hours or minutes) so it's not
        # possible to sort intra-day episodes properly. This is a hack
        # that tries to sort intra-day episodes in ascending order.
        # For example: https://areena.yle.fi/1-3863205
        if self._is_descending_date_based_playlist(playlist):
            playlist = reversed(playlist)

        # Sort in ascending order: first by episode number, then by date
        playlist = sorted(playlist, key=lambda x: x.sort_key())

        # The episode API doesn't seem to have any way to download only the
        # latest episode or start from the latest. We need to download all and
        # pick the latest.
        if latest_only:
            playlist = playlist[-1:]

        return [x.uri for x in playlist]

    def _episode_numbers_are_rare(self, playlist):
        num_has_episode = sum(p.episode_number is not None for p in playlist)
        return num_has_episode < 0.5 * len(playlist)

    def _timestamps_are_common(self, playlist):
        num_has_timestamp = sum(p.release_date is not None for p in playlist)
        return num_has_timestamp > 0.8 * len(playlist)

    def _is_descending_date_based_playlist(self, playlist):
        if not all(p.episode_number is None for p in playlist):
            return False

        prev_ts = None
        for p in playlist:
            if (
                prev_ts is not None
                and p.release_date is not None
                and p.release_date < prev_ts
            ):
                return True

            prev_ts = p.release_date

        return False

    def _download_playlist(self, season_urls):
        playlist = []
        for season_num, season_url in season_urls:
            # Areena server fails (502 Bad gateway) if page_size is larger
            # than 100.
            page_size = 100
            offset = 0
            has_next_page = True
            while has_next_page:
                logger.debug(
                    f'Getting a playlist page, season = {season_num}, '
                    f'size = {page_size}, offset = {offset}'
                )

                params = {
                    'offset': str(offset),
                    'limit': str(page_size),
                    'app_id': 'areena-web-items',
                    'app_key': 'wlTs5D9OjIdeS9krPzRQR4I1PYVzoazN',
                }
                playlist_page_url = update_url_query(season_url, params)
                page = self._parse_series_episode_data(playlist_page_url, season_num)

                if page is None:
                    logger.warning(
                        f'Playlist failed at offset {offset}. Some episodes may be missing!'
                    )
                    break

                playlist.extend(page)
                offset += len(page)
                has_next_page = len(page) == page_size

        return playlist

    def _parse_series_episode_data(self, playlist_page_url, season_number):
        playlist = self.httpclient.download_json(playlist_page_url)
        if playlist is None:
            return None

        episodes = []
        for data in playlist.get('data', []):
            uri = self._episode_uri(data)
            episode_number = self._episode_number(data)
            release_date = self._tv_release_date(data) or self._radio_release_date(data)

            if uri:
                episodes.append(
                    EpisodeMetadata(uri, season_number, episode_number, release_date)
                )

        return episodes

    @staticmethod
    def _extract_package_id(tree):
        package_id = tree.xpath('/html/body/@data-package-id')
        if package_id:
            return package_id[0]
        else:
            return None

    @staticmethod
    def _episode_uri(data):
        program_uri = data.get('pointer', {}).get('uri')
        if program_uri:
            media_id = program_uri.rsplit('/')[-1]
            return f'https://areena.yle.fi/{media_id}'
        else:
            return None

    @staticmethod
    def _episode_number(data):
        title = data.get('title')
        if title:
            # Try to parse the episode number from the title. That's the
            # only location where the episode number is available in the
            # API response.
            m = re.match(r'Jakso (\d+)', title, flags=re.IGNORECASE)
            if m:
                return int(m.group(1))

        return None

    def _tv_release_date(self, data):
        labels = data.get('labels')
        generics = self._label_by_type(labels, 'generic', 'formatted')
        for val in generics:
            # Look for a label that matches the format "pe 15.3.2019"
            m = re.match(
                r'[a-z]{2} (?P<day>\d{1,2})\.(?P<month>\d{1,2})\.(?P<year>\d{4})', val
            )
            if m:
                return datetime(
                    int(m.group('year')), int(m.group('month')), int(m.group('day'))
                )

        return None

    def _radio_release_date(self, data):
        labels = data.get('labels')
        date_str = self._label_by_type(labels, 'releaseDate', 'raw')
        if date_str:
            try:
                return parse_areena_timestamp(date_str[0])
            except ValueError:
                pass

        return None

    def _label_by_type(self, labels: dict, type_name: str, key_name: str) -> List[str]:
        """Return a key value of an Areena API label object which as the given type."""
        matches = [x for x in labels if x.get('type') == type_name]
        return [x[key_name] for x in matches if key_name in x]
