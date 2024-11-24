from datetime import datetime
import logging
import re
from .localization import TranslationChooser
from .subtitles import Subtitle
from .timestamp import parse_areena_timestamp, format_finnish_short_weekday_and_date


logger = logging.getLogger('yledl')


class AreenaPreviewApiParser:
    def __init__(self, data):
        self.preview = data or {}

    def media_id(self):
        ongoing = self.ongoing()
        mid1 = ongoing.get('media_id')
        mid2 = ongoing.get('adobe', {}).get('yle_media_id')
        return mid1 or mid2

    def duration_seconds(self):
        return self.ongoing().get('duration', {}).get('duration_in_seconds')

    def title(self, language_chooser):
        title = {}
        ongoing = self.ongoing()
        title_object = ongoing.get('title', {})
        if title_object:
            title['title'] = language_chooser.choose_long_form(title_object).strip()

        series_title_object = ongoing.get('series', {}).get('title', {})
        if series_title_object:
            title['series_title'] = language_chooser.choose_long_form(
                series_title_object
            ).strip()

        # If title['title'] does not equal title['episode_title'], then
        # the episode title is title['title'].
        #
        # If title['title'] equals title['episode_title'], then either
        # 1. the episode title is the publication date ("pe 16.9.2022"), or
        # 2. the episode title is title['title']
        #
        # It seem impossible to decide which of the cases 1. or 2. should apply
        # based on the preview API response only. We will always use the date
        # (case 1.) because that is the more common case.
        if title.get('title') is not None and title.get('title') == title.get(
            'series_title'
        ):
            title_timestamp = parse_areena_timestamp(ongoing.get('start_time'))
            if title_timestamp:
                # Should be localized (Finnish or Swedish) based on language_chooser
                title['title'] = format_finnish_short_weekday_and_date(title_timestamp)

        return title

    def description(self, language_chooser):
        description_object = self.ongoing().get('description', {})
        if not description_object:
            return None

        description_text = language_chooser.choose_long_form(description_object) or ''
        return description_text.strip()

    def season_and_episode(self):
        res = {}
        episode = self.ongoing().get('episode_number')
        if episode is not None:
            res = {'episode': episode}

            desc = self.description(TranslationChooser(['fin'])) or ''
            m = re.match(r'Kausi (\d+)\b', desc)
            if m:
                res.update({'season': int(m.group(1))})

        return res

    def available_at_region(self):
        return self.ongoing().get('region')

    def timestamp(self):
        if self.is_live():
            return datetime.now().replace(microsecond=0)
        else:
            dt = self.ongoing().get('start_time')
            return parse_areena_timestamp(dt)

    def manifest_url(self):
        return self.ongoing().get('manifest_url')

    def media_url(self):
        return self.ongoing().get('media_url')

    def media_type(self):
        if not self.preview:
            return None
        elif self.ongoing().get('content_type') == 'AudioObject':
            return 'audio'
        else:
            return 'video'

    def is_live(self):
        data = self.preview.get('data', {})
        return 'ongoing_channel' in data or 'ongoing_event' in data

    def is_pending(self):
        data = self.preview.get('data', {})
        pending = data.get('pending_event') or data.get('pending_ondemand')
        return pending is not None

    def is_expired(self):
        data = self.preview.get('data', {})
        return data.get('gone') is not None

    def ongoing(self):
        data = self.preview.get('data', {})
        return (
            data.get('ongoing_ondemand')
            or data.get('ongoing_event', {})
            or data.get('ongoing_channel', {})
            or data.get('pending_event')
            or {}
        )

    def subtitles(self):
        langname2to3 = {
            'fi': 'fin',
            'fih': 'fin',
            'sv': 'swe',
            'svh': 'swe',
            'se': 'smi',
            'en': 'eng',
        }
        hearing_impaired_langs = ['fih', 'svh']

        sobj = self.ongoing().get('subtitles', [])
        subtitles = []
        for s in sobj:
            # Areena has two subtitle objects. The newer object has "language"
            # and "kind" properties. "language" is a three-letter language code.
            lcode_longform = s.get('language', None)
            # The older (not used anymore as of Nov 2023?) format has "lang",
            # which is a two-letter language code with a possible third letter
            # "h" indicating hard-of-hearing subtitles.
            lcode = s.get('lang', None)

            if lcode_longform:
                lang = lcode_longform
                if s.get('kind', None) == 'hardOfHearing':
                    category = 'ohjelmatekstitys'
                else:
                    category = 'käännöstekstitys'
            elif lcode:
                lang = langname2to3.get(lcode, lcode)
                if lcode in hearing_impaired_langs:
                    category = 'ohjelmatekstitys'
                else:
                    category = 'käännöstekstitys'
            else:
                lang = 'unk'
                category = 'käännöstekstitys'
            url = s.get('uri', None)
            if lang and url:
                subtitles.append(Subtitle(url, lang, category))
        return subtitles
