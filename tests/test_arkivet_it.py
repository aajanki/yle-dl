# -*- coding: utf-8 -*-

import sys
import pytest
from utils import fetch_title, fetch_stream_url

@pytest.mark.skipif(sys.version_info < (2,7),
                    reason="SSL broken on Python 2.6")
def test_arkivet_title():
    title = fetch_title('http://svenska.yle.fi/artikel/2014/06/13'
                        '/halla-det-ar-naturvaktarna')

    assert title
    assert title[0] == 'Seportage om Naturväktarna'


@pytest.mark.skipif(sys.version_info < (2,7),
                    reason="SSL broken on Python 2.6")
def test_arkivet_stream_url():
    streamurl = fetch_stream_url('http://svenska.yle.fi/artikel/2014/06/13'
                                 '/halla-det-ar-naturvaktarna')
    assert streamurl
    assert 'manifest.f4m' in streamurl[0]
