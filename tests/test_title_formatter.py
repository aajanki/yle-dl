# -*- coding: utf-8 -*-

from __future__ import print_function, absolute_import, unicode_literals
import pytest
from datetime import datetime, date
from yledl.titleformatter import TitleFormatter

tf = TitleFormatter()


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
    title = tf.format('Uutiset: Kymmenen uutiset',
                      subheading='Uutiset')
    assert title == 'Uutiset: Kymmenen uutiset'


def test_season_and_episode():
    title = tf.format('Isänmaan toivot', season=2, episode=6)
    assert title == 'Isänmaan toivot: S02E06'


def test_remove_genre_prefix():
    assert tf.format('Elokuva: Indiana Jones') == 'Indiana Jones'


def test_series_title():
    title = tf.format('Kerblam!', series_title='Doctor Who')
    assert title == 'Doctor Who: Kerblam!'


def test_no_repeated_series_title():
    title = tf.format('Doctor Who', series_title='Doctor Who')
    assert title == 'Doctor Who'


def test_no_repeated_series_title_2():
    title = tf.format('Doctor Who: Kerblam!', series_title='Doctor Who')
    assert title == 'Doctor Who: Kerblam!'
