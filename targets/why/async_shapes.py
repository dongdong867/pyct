import asyncio
import contextlib


@contextlib.asynccontextmanager
async def held():
    yield 1


async def use_async_with(x: int) -> int:
    async with held() as h:
        if x != x:
            return h
    return 0


def async_with(x: int) -> int:
    return asyncio.run(use_async_with(x))


async def agen(x: int):
    yield 1
    y = 2
    yield y


async def first_of(x: int) -> int:
    g = agen(x)
    v = await g.__anext__()
    await g.aclose()
    return v


def async_gen(x: int) -> int:
    return asyncio.run(first_of(x))


def guarded_gen(x: int):
    try:
        yield 1
        z = 2
        yield z
    finally:
        w = 3


def yield_in_finally(x: int) -> int:
    g = guarded_gen(x)
    v = next(g)
    g.close()
    return v


def genexpr(x: int) -> int:
    return next(v for v in range(3) if v >= 0)


async def one(v: int) -> int:
    await asyncio.sleep(0)
    return v


async def gathered(x: int) -> list:
    return [await one(v) for v in range(2) if x != x]


def await_in_comprehension(x: int) -> list:
    return asyncio.run(gathered(x))
