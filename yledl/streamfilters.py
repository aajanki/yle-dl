import attr
from .backends import Backends


@attr.frozen
class StreamFilters:
    """Parameters for deciding which of potentially multiple available stream
    versions to download.
    """
    latest_only = attr.field(default=False)
    maxbitrate = attr.field(default=None)
    maxheight = attr.field(default=None)
    enabled_backends = attr.field(default=attr.Factory(
        lambda: list(Backends.default_order)
    ))
