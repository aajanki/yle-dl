import pytest
from yledl.subtitles import delay_substitles_srt_text

srt = """1
00:00:00,000 --> 00:00:02,500
Testing subtitles

2
00:00:03,000 --> 00:00:06,000
Subtitles are cool!

3
00:00:07,000 --> 00:00:10,230
Very long subtitles can consists of
multiple lines

4
01:59:12,280 --> 01:59:15,740
The end
"""

srt_delayed_2s = """1
00:00:02,000 --> 00:00:04,500
Testing subtitles

2
00:00:05,000 --> 00:00:08,000
Subtitles are cool!

3
00:00:09,000 --> 00:00:12,230
Very long subtitles can consists of
multiple lines

4
01:59:14,280 --> 01:59:17,740
The end
"""

srt_delayed_2min_500ms = """1
00:02:00,500 --> 00:02:03,000
Testing subtitles

2
00:02:03,500 --> 00:02:06,500
Subtitles are cool!

3
00:02:07,500 --> 00:02:10,730
Very long subtitles can consists of
multiple lines

4
02:01:12,780 --> 02:01:16,240
The end
"""

srt_advance_3s_400ms = """1
00:00:00,000 --> 00:00:00,000
Testing subtitles

2
00:00:00,000 --> 00:00:02,600
Subtitles are cool!

3
00:00:03,600 --> 00:00:06,830
Very long subtitles can consists of
multiple lines

4
01:59:08,880 --> 01:59:12,340
The end
"""


@pytest.mark.parametrize(
    'test_input,delay,expected',
    [
        (srt, 2000, srt_delayed_2s),
        (srt, 120_500, srt_delayed_2min_500ms),
        (srt, -3400, srt_advance_3s_400ms),
    ],
)
def test_delay_srt(test_input, delay, expected):
    delayed = delay_substitles_srt_text(test_input, delay)
    assert delayed == expected
