"""Classes that answer a field with code of their own, or store it plainly, for the reader of an
instance's stored fields. Each hook writes a file of its own name in the folder
``PYCT_TEST_HOOKS`` names, so a test sees whether any ran."""

import enum
import os


def touched(name: str) -> None:
    """Write the file ``name`` in the hooks folder: the hook ran."""
    with open(os.path.join(os.environ["PYCT_TEST_HOOKS"], name), "a") as log:
        log.write(f"{os.getpid()}\n")


class Plain:
    def __init__(self, code: object) -> None:
        self.code = code

    def cancel(self) -> int:
        touched("cancel")
        return 1


class Prop:
    def __init__(self, code: str) -> None:
        self._code = code

    @property
    def code(self) -> str:
        touched("property")
        return self._code


class Answering:
    def __init__(self, code: str) -> None:
        self.stored = code

    def __getattr__(self, name: str) -> str:
        touched("__getattr__")
        return "0"


class Gated:
    def __init__(self, code: str) -> None:
        self.code = code

    def __getattribute__(self, name: str) -> object:
        touched("__getattribute__")
        return object.__getattribute__(self, name)


class Slots:
    __slots__ = ("code",)

    def __init__(self, code: str | None = None) -> None:
        if code is not None:
            self.code = code


class PropOverSlot(Slots):
    __slots__ = ()

    def __init__(self, code: str) -> None:
        vars(Slots)["code"].__set__(self, code)

    @property
    def code(self) -> str:  # pyrefly: ignore[bad-override]
        touched("property over a slot")
        return "x"


class BorrowedSlot:
    """A class that holds another class's slot under its own name."""

    code = vars(Slots)["code"]


class BorrowedDict:
    """A class whose ``__dict__`` is another class's getter, which reads no instance of it."""

    __slots__ = ("__weakref__",)
    __dict__ = vars(Plain)["__dict__"]  # pyrefly: ignore[bad-override]


class DictProp:
    def __init__(self, code: str) -> None:
        object.__setattr__(self, "code", code)

    @property
    def __dict__(self) -> dict[str, str]:  # pyrefly: ignore[bad-override]
        touched("__dict__ property")
        return {"code": "fake"}


class Desc:
    def __get__(self, obj: object, owner: object = None) -> str:
        touched("__get__")
        return "1"

    def __set__(self, obj: object, value: object) -> None:
        touched("__set__")


class DataDesc:
    code = Desc()


class Meta(type):
    def __eq__(cls, other: object) -> bool:
        touched("metaclass __eq__")
        return NotImplemented

    def __hash__(cls) -> int:
        touched("metaclass __hash__")
        return 1

    def __getattribute__(cls, name: str) -> object:
        touched("metaclass __getattribute__")
        return type.__getattribute__(cls, name)


class WithMeta(metaclass=Meta):
    def __init__(self, code: str) -> None:
        self.code = code


class ClassProp:
    def __init__(self, code: str) -> None:
        self.code = code

    @property
    def __class__(self) -> type:  # pyrefly: ignore[bad-override]
        touched("__class__ property")
        return str


class SameHash:
    """A key of the same hash as ``"code"``, whose ``__eq__`` would answer a lookup of it once
    ``armed``; the dict it goes into compares it as it is stored."""

    armed = False

    def __hash__(self) -> int:
        return hash("code")

    def __eq__(self, other: object) -> bool:
        if SameHash.armed:
            touched("key __eq__")
        return False


class ClassOnly:
    code = "0"


class Code(str):
    def __eq__(self, other: object) -> bool:
        touched("str subclass __eq__")
        return False

    __hash__ = str.__hash__


class Level(enum.IntEnum):
    LOW = 1


class Tagged(list[object]):
    pass


class MetaValue(metaclass=Meta):
    pass
