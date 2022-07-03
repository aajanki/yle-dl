import attr


@attr.frozen
class Subtitle:
    url: str
    lang: str
    category: str


@attr.frozen
class EmbeddedSubtitle:
    language: str
    category: str
