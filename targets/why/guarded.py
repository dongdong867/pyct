import asyncio


def with_in_branch(x: int) -> str:
    if x != x:
        with open("/dev/null") as f:
            return f"never {f.closed}"
    return "always"


def comp_in_branch(x: int) -> object:
    if x != x:
        ys = [i for i in range(3)]
        return ys
    return "always"


def finally_in_branch(x: int) -> str:
    if x != x:
        try:
            y = 1
        finally:
            y = 2
        return f"never {y}"
    return "always"


def except_in_branch(x: int) -> object:
    if x != x:
        try:
            return int("q")
        except ValueError as e:
            return str(e)
    return "always"


async def waits(x: int) -> int:
    if x != x:
        await asyncio.sleep(0)
        return 1
    return 2


def awaited(x: int) -> int:
    return asyncio.run(waits(x))
