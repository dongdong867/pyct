import asyncio


async def co(x: int) -> int:
    await asyncio.sleep(0)
    return 1


def at_await(x: int) -> int:
    c = co(x)
    c.send(None)
    # stops asking: the coroutine stays at its await
    c.close()
    return 0
