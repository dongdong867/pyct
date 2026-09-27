"""A sweep fixture: the class whose method another module exposes bound."""


class Parser:
    def parse(self, text: str) -> str:
        if text == "x":
            return "one"
        return text
