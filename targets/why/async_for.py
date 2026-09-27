import asyncio


async def agen(x: int):
    yield 1
    yield 2


async def use_async_for(x: int) -> int:
    async for v in agen(x):
        return v
    return 0


def async_for(x: int) -> int:
    return asyncio.run(use_async_for(x))
