class Crate:
    def __len__(self) -> int:
        return 1 // 0


def sized(n: int) -> str:
    if len(n) > 3:  # pyrefly: ignore[bad-argument-type]
        return "long"
    return "short"


def below_zero(x: int) -> str:
    return chr(-1)


def crate(x: int) -> int:
    return len(Crate()) + x
