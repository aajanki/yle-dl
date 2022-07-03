import attr
from .backends import FailingBackend


@attr.define
class StreamFlavor:
    media_type = attr.field()
    height = attr.field(default=None, converter=attr.converters.optional(int))
    width = attr.field(default=None, converter=attr.converters.optional(int))
    bitrate = attr.field(default=None, converter=attr.converters.optional(int))
    streams = attr.field(factory=list)


class FailedFlavor(StreamFlavor):
    def __init__(self, error_message):
        StreamFlavor.__init__(self,
                              media_type='unknown',
                              height=None,
                              width=None,
                              bitrate=None,
                              streams=[FailingBackend(error_message)])
