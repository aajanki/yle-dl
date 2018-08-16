# -*- coding: utf-8 -*-

from __future__ import print_function, absolute_import, unicode_literals
import pytest
from yledl.extractors import TitleFormatter


f = TitleFormatter


def test_none_title():
    assert f().title(None, None) is None


def test_title_only():
    assert f().title('test', None) == 'test'


def test_title_timestamp():
    title = f().title('test', '2018-01-02T03:04:05')
    assert title == 'test-2018-01-02T03:04:05'


def test_subheading():
    title = f().title('EM-kisat', None, subheading='Kymmenottelu')
    assert title == 'EM-kisat: Kymmenottelu'


def test_no_repeated_subheading():
    title = f().title('Uutiset: Kymmenen uutiset', None, subheading='Uutiset')
    assert title == 'Uutiset: Kymmenen uutiset'


def test_season_and_episode():
    title = f().title('Isänmaan toivot', None, season=2, episode=6)
    assert title == 'Isänmaan toivot: S02E06'


def test_remove_genre_prefix():
    assert f().title('Elokuva: Indiana Jones', None) == 'Indiana Jones'
