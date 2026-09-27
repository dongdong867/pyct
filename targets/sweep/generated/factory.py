"""A sweep fixture: a factory that returns a function it defines inside itself."""


def make_parser():
    def parse(text):
        return text.strip()

    return parse
