"""A sweep fixture: a package that puts a module object in its place which forwards every name,
__path__ included, to the package, as a deprecation wrapper does."""

import sys
import types


class _Forward(types.ModuleType):
    def __init__(self, module: types.ModuleType) -> None:
        super().__init__(module.__name__)
        self._module = module

    def __getattr__(self, name: str) -> object:
        return getattr(self._module, name)


sys.modules[__name__] = _Forward(sys.modules[__name__])
