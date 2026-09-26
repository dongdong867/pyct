import os


def speak(x: int) -> str:
    print("hello")
    os.write(1, b"raw\n")
    if x > 3:
        return "big"
    return "small"
