"""A sweep fixture: a function exec builds, and one another module's factory built."""

from .factory import make_parser

exec("def made(n):\n    return n + 1\n")

parse = make_parser()
