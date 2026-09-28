def hold(x: int) -> str:
    try:
        raise KeyboardInterrupt
    except KeyboardInterrupt:
        # a handler that never returns, so the Ctrl-C it handles never leaves
        while True:
            pass
