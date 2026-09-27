import asyncio


def looping(x: int):
    while True:
        a = x
        yield a
        x += 1


def takes_one(x: int) -> int:
    return next(looping(x))


def looping_raise(x: int):
    while True:
        v = yield 1
        w = {}[v]
        yield w


def resumed_raise(x: int) -> int:
    g = looping_raise(x)
    next(g)
    try:
        g.send("k")
    except KeyError:
        return 0
    return 1


async def aloop(x: int):
    while True:
        yield x
        x += 1


async def take_async(x: int) -> int:
    g = aloop(x)
    v = await g.__anext__()
    await g.aclose()
    return v


def run_async(x: int) -> int:
    return asyncio.run(take_async(x))
