"""A class whose constructor's signature Python cannot read, with a method that runs on an
instance each input builds."""


class Sealed:
    # inspect reads a class's signature here first, and refuses what is not one
    __signature__ = 5

    def __init__(self, n: int):
        self.n = n

    def check(self):
        if self.n > 0:
            return "positive"
        return "other"
