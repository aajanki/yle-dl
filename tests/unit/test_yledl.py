import pytest

from yledl.yledl import arg_parser


@pytest.fixture
def parser(monkeypatch, tmp_path):
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path))
    return arg_parser()


@pytest.mark.parametrize('option', ['-d', '--delay'])
@pytest.mark.parametrize(
    'value, expected', [('0', 0.0), ('10', 10.0), ('0.5', 0.5), ('1,5', 1.5)]
)
def test_delay_argument(parser, option, value, expected):
    assert parser.parse_args([option, value]).delay == expected


def test_delay_defaults_to_zero(parser):
    assert parser.parse_args([]).delay == 0.0


def test_delay_from_config_file(parser, tmp_path):
    config = tmp_path / 'yledl.conf'
    config.write_text('delay=3.5\n')

    assert parser.parse_args(['--config', str(config)]).delay == 3.5
    assert parser.parse_args(['--config', str(config), '-d', '1']).delay == 1.0


@pytest.mark.parametrize('value', ['-1', 'nan', 'inf', '-inf', 'invalid'])
def test_invalid_delay_argument(parser, value):
    with pytest.raises(SystemExit) as exc:
        parser.parse_args([f'--delay={value}'])
    assert exc.value.code == 2
