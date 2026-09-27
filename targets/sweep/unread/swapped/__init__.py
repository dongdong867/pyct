"""A sweep fixture: a package that puts an object with no __name__ in its own place."""

import sys


class _Facade:
    pass


_facade = _Facade()
_facade.__path__ = __path__
_facade.__spec__ = __spec__
sys.modules[__name__] = _facade
