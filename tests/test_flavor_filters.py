# -*- coding: utf-8 -*-

import pytest
from yledl.downloaders import filter_flavors


flavors = [
    {"id": 1, "bitrate": 190, "width": 224, "height": 126},

    {"id": 5, "bitrate": 1506, "width": 1280, "height": 720},
    {"id": 6, "bitrate": 2628, "width": 1280, "height": 720},
    {"id": 7, "bitrate": 4128, "width": 1920, "height": 1080},

    {"id": 4, "bitrate": 964, "width": 640, "height": 360},
    {"id": 3, "bitrate": 668, "width": 640, "height": 360},
    {"id": 2, "bitrate": 469, "width": 640, "height": 360}
]


def test_empty_input():
    assert filter_flavors([], None, None) == {}
    assert filter_flavors([], 720, None) == {}
    assert filter_flavors([], None, 5000) == {}
    assert filter_flavors([], 720, 5000) == {}


def test_no_filters():
    assert filter_flavors(flavors, None, None)['id'] == 7


def test_bitrate_filter():
    assert filter_flavors(flavors, None, 10)['id'] == 1
    assert filter_flavors(flavors, None, 200)['id'] == 1
    assert filter_flavors(flavors, None, 963)['id'] == 3
    assert filter_flavors(flavors, None, 964)['id'] == 4
    assert filter_flavors(flavors, None, 1000)['id'] == 4
    assert filter_flavors(flavors, None, 5000)['id'] == 7


def test_resolution_filter():
    assert filter_flavors(flavors, 100, None)['id'] == 1
    assert filter_flavors(flavors, 480, None)['id'] == 2
    assert filter_flavors(flavors, 719, None)['id'] == 2
    assert filter_flavors(flavors, 720, None)['id'] == 5
    assert filter_flavors(flavors, 1080, None)['id'] == 7
    assert filter_flavors(flavors, 2160, None)['id'] == 7


def test_combined_filters():
    assert filter_flavors(flavors, 10, 10)['id'] == 1
    assert filter_flavors(flavors, 200, 10)['id'] == 1
    assert filter_flavors(flavors, 10, 200)['id'] == 1
    assert filter_flavors(flavors, 360, 400)['id'] == 1
    assert filter_flavors(flavors, 360, 650)['id'] == 2
    assert filter_flavors(flavors, 360, 700)['id'] == 3
    assert filter_flavors(flavors, 360, 5000)['id'] == 4
    assert filter_flavors(flavors, 720, 200)['id'] == 1
    assert filter_flavors(flavors, 2160, 1506)['id'] == 5
