"""A sweep fixture: parameters hinted with a plain type beside None, whose default is None."""


class Filter:
    def __init__(self, language: str | None = None) -> None:
        self.language = language

    def keep(self, url: str) -> bool:
        if self.language is None:
            return True
        return url.startswith(self.language)


def lang_filter(url: str, language: str | None = None) -> bool:
    if language is None:
        return True
    if language == "en":
        return url.startswith("en")
    return False


def make_time(frames: int | None = None, fps: float | None = None) -> float:
    if frames is None or fps is None:
        return 0.0
    return frames / fps if fps else 0.0


def screen(rule: Filter) -> bool:
    return rule.keep("en")
