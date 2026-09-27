from targets.intercept import sized_helper


class Ruler:
    def longer(self, s: str) -> bool:
        if len(s) > 4:
            return True
        return False


def spread(s: str) -> list[bool]:
    def nested() -> bool:
        if len(s) > 5:
            return True
        return False

    return [sized_helper.longer(s), Ruler().longer(s), nested()]
