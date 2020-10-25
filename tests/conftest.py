import pytest


def pytest_addoption(parser):
    parser.addoption('--geoblocked', action='store_true',
                     help='Enable get-blocked tests that work only in Finland')


def pytest_configure(config):
    config.addinivalue_line("markers", "geoblocked: get-blocked test that work only in Finland")


def pytest_collection_modifyitems(config, items):
    if not config.option.geoblocked:
        # Skip tests marked as geoblocked
        skip_geoblocked = pytest.mark.skip(reason="need --geoblocked option to run")
        for item in items:
            if "geoblocked" in item.keywords:
                item.add_marker(skip_geoblocked)
