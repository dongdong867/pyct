def ask(x: int) -> str:
    answer = input()
    if x > 3:
        return f"big {answer}"
    return f"small {answer}"
