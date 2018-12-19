# -*- coding: utf-8 -*-

from __future__ import print_function, absolute_import, unicode_literals
import pytest
from datetime import datetime, date, timedelta, timezone
from yledl.titleformatter import TitleFormatter

tf = TitleFormatter()


@pytest.fixture
def pasila():
    return {
        'title': 'Vanhempainyhdistys',
        'publish_timestamp': datetime(
            2018, 4, 12, 16, 30, 45,
            tzinfo=timezone(timedelta(hours=2))),
        'series_title': 'Pasila',
        'subheading':'tekstitys englanniksi',
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


def test_no_repeated_series_title_with_episode_title():
    title = tf.format('Doctor Who: Kerblam!', series_title='Doctor Who')
    assert title == 'Doctor Who: Kerblam!'


def test_all_components(pasila):
    assert tf.format(**pasila) == 'Pasila: Vanhempainyhdistys: '\
        'tekstitys englanniksi: S01E03-2018-04-12T16:30'


def test_template(pasila):
    tf = TitleFormatter('${series}${title}${episode}${timestamp}')
    assert tf.format(**pasila) == 'Pasila: Vanhempainyhdistys: '\
        'tekstitys englanniksi: S01E03-2018-04-12T16:30'

    tf = TitleFormatter('${series}${episode}${timestamp}')
    assert tf.format(**pasila) == 'Pasila: S01E03-2018-04-12T16:30'

    tf = TitleFormatter('${title}${timestamp}')
    assert tf.format(**pasila) == 'Vanhempainyhdistys: '\
        'tekstitys englanniksi-2018-04-12T16:30'

    tf = TitleFormatter('${timestamp}${title}')
    assert tf.format(**pasila) == '2018-04-12T16:30: '\
        'Vanhempainyhdistys: tekstitys englanniksi'


def test_template_literal(pasila):
    tf = TitleFormatter('Areena ${series}${episode}')
    assert tf.format(**pasila) == 'Areena : Pasila: S01E03'

    tf = TitleFormatter('${series} Areena${episode}')
    assert tf.format(**pasila) == 'Pasila Areena: S01E03'

    tf = TitleFormatter('${series}${episode} Areena')
    assert tf.format(**pasila) == 'Pasila: S01E03 Areena'

    tf = TitleFormatter('Areena ${series} Areena${episode} Areena')
    assert tf.format(**pasila) == 'Areena : Pasila Areena: S01E03 Areena'


def test_template_duplicate_key(pasila):
    tf = TitleFormatter('${series}${series}')
    assert tf.format(**pasila) == 'Pasila: Pasila'


def test_unknown_templates_are_not_substituted(pasila):
    tf = TitleFormatter('${series}${invalid}${timestamp}')
    assert tf.format(**pasila) == 'Pasila: ${invalid}-2018-04-12T16:30'


def test_unclosed_template(pasila):
    tf = TitleFormatter('${series}${timestamp')
    assert tf.format(**pasila) == 'Pasila${timestamp'

    tf = TitleFormatter('${series}${title${timestamp}')
    assert tf.format(**pasila) == 'Pasila${title-2018-04-12T16:30'


def test_template_incorrectly_balanced_brackets(pasila):
    tf = TitleFormatter('${series}${title${timestamp}}')
    assert tf.format(**pasila) == 'Pasila${title-2018-04-12T16:30}'
