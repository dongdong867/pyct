import gettext

from targets.translated import words


def main(x: int) -> list[str]:
    gettext.install("pyct-none")
    if x > 0:
        return [words.greet(), words.shout()]
    return []
