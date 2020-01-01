# -*- coding: utf-8 -*-

from __future__ import print_function, absolute_import, unicode_literals
import pytest
from datetime import datetime, date
from yledl.timestamp import FixedOffset
from yledl.titleformatter import TitleFormatter

tf = TitleFormatter()


@pytest.fixture
def pasila():
    return {
        'title': 'Vanhempainyhdistys',
        'publish_timestamp': datetime(
            2018, 4, 12, 16, 30, 45,
            tzinfo=FixedOffset(2)),
        'series_title': 'Pasila',
        'subheading':'tekstitys englanniksi',
        'program_id': '1-86743',
        'season': 1,
        'episode': 3,
    }


def test_none_title():
    assert tf.format(None) is None


def test_title_only():
    assert tf.format('test') == 'test'


def test_title_timestamp():
    title = tf.format('test', publish_timestamp=datetime(2018, 1, 2, 3, 4, 5))
    assert title == 'test-2018-01-02T03:04'


def test_title_date_only():
    title = tf.format('test', publish_timestamp=date(2018, 1, 2))
    assert title == 'test-2018-01-02'


def test_repeated_main_title():
    title = tf.format('Uutiset: Uutiset iltapäivällä')
    assert title == 'Uutiset iltapäivällä'


def test_subheading():
    title = tf.format('EM-kisat', subheading='Kymmenottelu')
    assert title == 'EM-kisat: Kymmenottelu'


def test_no_repeated_subheading():
    title = tf.format('Uutiset: Kymmenen uutiset', subheading='Uutiset')
    assert title == 'Uutiset: Kymmenen uutiset'


def test_season_and_episode():
    title = tf.format('Isänmaan toivot', season=2, episode=6)
    assert title == 'Isänmaan toivot: S02E06'


def test_episode_without_season():
    title = tf.format('Isänmaan toivot', episode=12)
    assert title == 'Isänmaan toivot: E12'


def test_remove_genre_prefix():
    assert tf.format('Elokuva: Indiana Jones') == 'Indiana Jones'


def test_series_title():
    title = tf.format('Kerblam!', series_title='Doctor Who')
    assert title == 'Doctor Who: Kerblam!'


def test_no_repeated_series_title():
    title = tf.format('Doctor Who', series_title='Doctor Who')
    assert title == 'Doctor Who'


def test_no_repeated_series_title_whole_words():
    title = tf.format('Noin viikon studion uusi vuosi',
                      series_title='Noin viikon studio')
    assert title == 'Noin viikon studio: Noin viikon studion uusi vuosi'


def test_no_repeated_series_title_with_subheading():
    title = tf.format('Solsidan', series_title='Solsidan',
                      subheading='Nya avsnitt från Solsidan')
    assert title == 'Solsidan: Nya avsnitt från Solsidan'


def test_no_repeated_series_title_with_episode_title():
    title = tf.format('Doctor Who: Kerblam!', series_title='Doctor Who')
    assert title == 'Doctor Who: Kerblam!'


def test_main_title_equals_series_title_plus_age_limit():
    title = tf.format('Rantahotelli (S)', series_title='Rantahotelli')
    assert title == 'Rantahotelli'


def test_strip_whitespace():
    title = tf.format(' Rantahotelli ')
    assert title == 'Rantahotelli'

    title = tf.format('Uutiset klo 18', series_title='Uutiset ')
    assert title == 'Uutiset: klo 18'

    title = tf.format('Uutiset klo 18', series_title=' Uutiset ')
    assert title == 'Uutiset: klo 18'


def test_all_components(pasila):
    assert tf.format(**pasila) == 'Pasila: Vanhempainyhdistys: '\
        'tekstitys englanniksi: S01E03-2018-04-12T16:30'


def test_template(pasila):
    fmt = TitleFormatter('${series}${title}${episode}${timestamp}')
    assert fmt.format(**pasila) == 'Pasila: Vanhempainyhdistys: '\
        'tekstitys englanniksi: S01E03-2018-04-12T16:30'

    fmt = TitleFormatter('${series}${episode}${timestamp}')
    assert fmt.format(**pasila) == 'Pasila: S01E03-2018-04-12T16:30'

    fmt = TitleFormatter('${title}${timestamp}')
    assert fmt.format(**pasila) == 'Vanhempainyhdistys: '\
        'tekstitys englanniksi-2018-04-12T16:30'

    fmt = TitleFormatter('${timestamp}${title}')
    assert fmt.format(**pasila) == '2018-04-12T16:30: '\
        'Vanhempainyhdistys: tekstitys englanniksi'

    fmt = TitleFormatter('${program_id}${series}')
    assert fmt.format(**pasila) == '1-86743: Pasila'

    fmt = TitleFormatter('${series}${program_id}')
    assert fmt.format(**pasila) == 'Pasila-1-86743'


def test_template_date(pasila):
    fmt = TitleFormatter('${series}${date}')
    assert fmt.format(**pasila) == 'Pasila-2018-04-12'

    fmt = TitleFormatter('${date}${series}')
    assert fmt.format(**pasila) == '2018-04-12: Pasila'

    fmt = TitleFormatter('${series}${date}${timestamp}')
    assert fmt.format(**pasila) == 'Pasila-2018-04-12-2018-04-12T16:30'


def test_template_series_duplicated_in_main_title():
    data = {
        'title': 'Jopet-show: Haikeaa joulua',
        'series_title': 'Jopet-show',
    }

    fmt = TitleFormatter('${series}')
    assert fmt.format(**data) == 'Jopet-show'

    fmt = TitleFormatter('${title}')
    assert fmt.format(**data) == 'Haikeaa joulua'

    fmt = TitleFormatter('${series}${title}')
    assert fmt.format(**data) == 'Jopet-show: Haikeaa joulua'


def test_template_series_equals_main_title():
    data = {
        'title': 'Rantahotelli',
        'series_title': 'Rantahotelli',
    }

    fmt = TitleFormatter('${series}')
    assert fmt.format(**data) == ''

    fmt = TitleFormatter('${title}')
    assert fmt.format(**data) == 'Rantahotelli'

    fmt = TitleFormatter('${series}${title}')
    assert fmt.format(**data) == 'Rantahotelli'


def test_template_literal(pasila):
    fmt = TitleFormatter('Areena ${series}${episode}')
    assert fmt.format(**pasila) == 'Areena : Pasila: S01E03'

    fmt = TitleFormatter('${series} Areena${episode}')
    assert fmt.format(**pasila) == 'Pasila Areena: S01E03'

    fmt = TitleFormatter('${series}${episode} Areena')
    assert fmt.format(**pasila) == 'Pasila: S01E03 Areena'

    fmt = TitleFormatter('Areena ${series} Areena${episode} Areena')
    assert fmt.format(**pasila) == 'Areena : Pasila Areena: S01E03 Areena'


def test_template_duplicate_key(pasila):
    fmt = TitleFormatter('${series}${series}')
    assert fmt.format(**pasila) == 'Pasila: Pasila'


def test_template_literal_dollar_sign(pasila):
    fmt = TitleFormatter('${series} 500$$ ABC')
    assert fmt.format(**pasila) == 'Pasila 500$ ABC'

    fmt = TitleFormatter('${series} 500$$ $$$$ ABC')
    assert fmt.format(**pasila) == 'Pasila 500$ $$ ABC'


def test_template_unbalanced_dollar_literals(pasila):
    fmt = TitleFormatter('${series} $$$ ABC')
    assert fmt.format(**pasila) == 'Pasila $$ ABC'


def test_unknown_templates_are_not_substituted(pasila):
    fmt = TitleFormatter('${series}${invalid}${timestamp}')
    assert fmt.format(**pasila) == 'Pasila: ${invalid}-2018-04-12T16:30'


def test_unclosed_template(pasila):
    fmt = TitleFormatter('${series}${timestamp')
    assert fmt.format(**pasila) == 'Pasila${timestamp'

    fmt = TitleFormatter('${series}${title${timestamp}')
    assert fmt.format(**pasila) == 'Pasila${title-2018-04-12T16:30'


def test_template_incorrectly_balanced_brackets(pasila):
    fmt = TitleFormatter('${series}${title${timestamp}}')
    assert fmt.format(**pasila) == 'Pasila${title-2018-04-12T16:30}'
