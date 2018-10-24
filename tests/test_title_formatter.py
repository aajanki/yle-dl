# -*- coding: utf-8 -*-

from __future__ import print_function, absolute_import, unicode_literals
import pytest
from yledl.titleformatter import TitleFormatter

tf = TitleFormatter()


def test_none_title():
    assert tf.format(None, None) is None


def test_title_only():
    assert tf.format('test', None) == 'test'


def test_title_timestamp():
    title = tf.format('test', '2018-01-02T03:04:05')
    assert title == 'test-2018-01-02T03:04'

def test_repeated_main_title():
    title = tf.format('Uutiset: Uutiset iltapäivällä', None)
    assert title == 'Uutiset iltapäivällä'

def test_subheading():
    title = tf.format('EM-kisat', None, subheading='Kymmenottelu')
    assert title == 'EM-kisat: Kymmenottelu'


def test_no_repeated_subheading():
    title = tf.format('Uutiset: Kymmenen uutiset', None, subheading='Uutiset')
    assert title == 'Uutiset: Kymmenen uutiset'


def test_season_and_episode():
    title = tf.format('Isänmaan toivot', None, season=2, episode=6)
    assert title == 'Isänmaan toivot: S02E06'


def test_remove_genre_prefix():
    assert tf.format('Elokuva: Indiana Jones', None) == 'Indiana Jones'
