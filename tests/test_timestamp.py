# -*- coding: utf-8 -*-

from datetime import datetime, timedelta
from yledl.timestamp import parse_areena_timestamp


def test_timestamp():
    ts = parse_areena_timestamp('2018-01-02T18:30:00+02:00')

    assert ts.replace(tzinfo=None) == datetime(2018, 1, 2, 18, 30, 00)
    assert ts.utcoffset() == timedelta(hours=2)

    
def test_timestamp_strip():
    ts = parse_areena_timestamp('  2018-01-02T18:30:00+02:00  ')
    assert ts.replace(tzinfo=None) == datetime(2018, 1, 2, 18, 30, 00)

def test_invalid_timestamp():
    assert parse_areena_timestamp('xxx2018-01-02T18:30:00+02:00') is None
    assert parse_areena_timestamp('2018-01-02T18:30:00') is None
    assert parse_areena_timestamp('2018-01-999999T18:30:00+02:00') is None
    assert parse_areena_timestamp('2018-01-999999T22222') is None
