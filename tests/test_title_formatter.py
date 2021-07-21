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


def test_title_timestamp():
    title = tf.format('test', publish_timestamp=datetime(2018, 1, 2, 3, 4, 5))
    assert title == 'test: 2018-01-02T03:04'


def test_title_date_only():
    title = tf.format('test', publish_timestamp=date(2018, 1, 2))
    assert title == 'test: 2018-01-02'


def test_repeated_main_title():
    title = tf.format('Uutiset: Uutiset iltapäivällä', publish_timestamp=date(2021, 1, 1))
    assert title == 'Uutiset iltapäivällä: 2021-01-01'


def test_subheading():
    title = tf.format('EM-kisat', subheading='Kymmenottelu', publish_timestamp=date(2021, 1, 1))
    assert title == 'EM-kisat: Kymmenottelu: 2021-01-01'


def test_no_repeated_subheading():
    title = tf.format('Uutiset: Kymmenen uutiset', subheading='Uutiset', publish_timestamp=date(2021, 1, 1))
    assert title == 'Uutiset: Kymmenen uutiset: 2021-01-01'


def test_season_and_episode():
    title = tf.format('Isänmaan toivot', season=2, episode=6, publish_timestamp=date(2021, 1, 1))
    assert title == 'Isänmaan toivot: S02E06-2021-01-01'


def test_episode_without_season():
    title = tf.format('Isänmaan toivot', episode=12, publish_timestamp=date(2021, 1, 1))
    assert title == 'Isänmaan toivot: E12-2021-01-01'


def test_remove_genre_prefix():
    assert tf.format('Elokuva: Indiana Jones', publish_timestamp=date(2021, 1, 1)) == 'Indiana Jones: 2021-01-01'


def test_series_title():
    title = tf.format('Kerblam!', series_title='Doctor Who', publish_timestamp=date(2021, 1, 1))
    assert title == 'Doctor Who: Kerblam!: 2021-01-01'


def test_no_repeated_series_title():
    title = tf.format('Doctor Who', series_title='Doctor Who', publish_timestamp=date(2021, 1, 1))
    assert title == 'Doctor Who: 2021-01-01'


def test_no_repeated_series_title_whole_words():
    title = tf.format('Noin viikon studion uusi vuosi',
                      series_title='Noin viikon studio',
                      publish_timestamp=date(2021, 1, 1))
    assert title == 'Noin viikon studio: Noin viikon studion uusi vuosi: 2021-01-01'


def test_no_repeated_series_title_with_subheading():
    title = tf.format('Solsidan', series_title='Solsidan',
                      subheading='Nya avsnitt från Solsidan',
                      publish_timestamp=date(2021, 1, 1))
    assert title == 'Solsidan: Nya avsnitt från Solsidan: 2021-01-01'


def test_no_repeated_series_title_with_episode_title():
    title = tf.format('Doctor Who: Kerblam!', series_title='Doctor Who', publish_timestamp=date(2021, 1, 1))
    assert title == 'Doctor Who: Kerblam!: 2021-01-01'


def test_series_name_as_part_of_episode_title():
    title = tf.format('Rölli ja Robotti Ruttunen', series_title='Rölli', publish_timestamp=date(2021, 1, 1))
    assert title == 'Rölli: Rölli ja Robotti Ruttunen: 2021-01-01'


def test_main_title_equals_series_title_plus_age_limit():
    title = tf.format('Rantahotelli (S)', series_title='Rantahotelli', publish_timestamp=date(2021, 1, 1))
    assert title == 'Rantahotelli: 2021-01-01'


def test_strip_whitespace():
    title = tf.format(' Rantahotelli ', publish_timestamp=date(2021, 1, 1))
    assert title == 'Rantahotelli: 2021-01-01'

    title = tf.format('Uutiset klo 18', series_title='Uutiset ', publish_timestamp=date(2021, 1, 1))
    assert title == 'Uutiset: Uutiset klo 18: 2021-01-01'

    title = tf.format('Uutiset klo 18', series_title=' Uutiset ', publish_timestamp=date(2021, 1, 1))
    assert title == 'Uutiset: Uutiset klo 18: 2021-01-01'


def test_all_components(pasila):
    assert tf.format(**pasila) == 'Pasila: Vanhempainyhdistys: '\
        'tekstitys englanniksi: S01E03-2018-04-12T16:30'


def test_template(pasila):
    fmt = TitleFormatter('${series}: ${title}: ${episode}-${timestamp}')
    assert fmt.format(**pasila) == 'Pasila: Vanhempainyhdistys: '\
        'tekstitys englanniksi: S01E03-2018-04-12T16:30'

    fmt = TitleFormatter('${series}: ${episode}-${timestamp}')
    assert fmt.format(**pasila) == 'Pasila: S01E03-2018-04-12T16:30'

    fmt = TitleFormatter('${title}-${timestamp}')
    assert fmt.format(**pasila) == 'Vanhempainyhdistys: '\
        'tekstitys englanniksi-2018-04-12T16:30'

    fmt = TitleFormatter('${timestamp}: ${title}')
    assert fmt.format(**pasila) == '2018-04-12T16:30: '\
        'Vanhempainyhdistys: tekstitys englanniksi'

    fmt = TitleFormatter('${program_id}: ${series}')
    assert fmt.format(**pasila) == '1-86743: Pasila'

    fmt = TitleFormatter('${series}-${program_id}')
    assert fmt.format(**pasila) == 'Pasila-1-86743'


def test_template_date(pasila):
    fmt = TitleFormatter('${series}-${date}')
    assert fmt.format(**pasila) == 'Pasila-2018-04-12'

    fmt = TitleFormatter('${date}: ${series}')
    assert fmt.format(**pasila) == '2018-04-12: Pasila'

    fmt = TitleFormatter('${series}-${date}-${timestamp}')
    assert fmt.format(**pasila) == 'Pasila-2018-04-12-2018-04-12T16:30'


def test_template_series_duplicated_in_main_title():
    data = {
        'title': 'Jopet-show: Haikeaa joulua',
        'series_title': 'Jopet-show',
        'publish_timestamp': datetime(
            2018, 4, 12, 16, 30, 45,
            tzinfo=FixedOffset(2))
    }

    fmt = TitleFormatter('${series}')
    assert fmt.format(**data) == 'Jopet-show'

    fmt = TitleFormatter('${title}')
    assert fmt.format(**data) == 'Haikeaa joulua'

    fmt = TitleFormatter('${series}: ${title}')
    assert fmt.format(**data) == 'Jopet-show: Haikeaa joulua'


def test_template_series_equals_main_title():
    data = {
        'title': 'Rantahotelli',
        'series_title': 'Rantahotelli',
        'publish_timestamp': datetime(
            2018, 4, 12, 16, 30, 45,
            tzinfo=FixedOffset(2))
    }

    fmt = TitleFormatter('${series}')
    assert fmt.format(**data) == ''

    fmt = TitleFormatter('${title}')
    assert fmt.format(**data) == 'Rantahotelli'

    fmt = TitleFormatter('${series}${title}')
    assert fmt.format(**data) == 'Rantahotelli'


def test_template_literal(pasila):
    fmt = TitleFormatter('Areena ${series}-${episode}')
    assert fmt.format(**pasila) == 'Areena Pasila-S01E03'

    fmt = TitleFormatter('${series}: Areena-${episode}')
    assert fmt.format(**pasila) == 'Pasila: Areena-S01E03'

    fmt = TitleFormatter('${series}: ${episode} Areena')
    assert fmt.format(**pasila) == 'Pasila: S01E03 Areena'

    fmt = TitleFormatter('Areena: ${series} episode ${episode} Areena')
    assert fmt.format(**pasila) == 'Areena: Pasila episode S01E03 Areena'


def test_template_duplicate_key(pasila):
    fmt = TitleFormatter('${series}: ${series}')
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
    fmt = TitleFormatter('${series}: ${invalid}: ${timestamp}')
    assert fmt.format(**pasila) == 'Pasila: ${invalid}: 2018-04-12T16:30'


def test_unclosed_template(pasila):
    fmt = TitleFormatter('${series}: ${timestamp')
    assert fmt.format(**pasila) == 'Pasila: ${timestamp'

    fmt = TitleFormatter('${series}: ${title: ${timestamp}')
    assert fmt.format(**pasila) == 'Pasila: ${title: 2018-04-12T16:30'


def test_template_incorrectly_balanced_brackets(pasila):
    fmt = TitleFormatter('${series}: ${title: ${timestamp}}')
    assert fmt.format(**pasila) == 'Pasila: ${title: 2018-04-12T16:30}'
