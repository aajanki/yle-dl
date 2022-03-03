import attr


@attr.s
class Subtitle:
    url = attr.ib()
    lang = attr.ib()
    category = attr.ib()


@attr.s
class EmbeddedSubtitle:
    language = attr.ib()
    category = attr.ib()
