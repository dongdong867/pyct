"""The environment a ``RunResult`` carries where the value itself does not matter.

A run gathers its own; a unit test that is about something else takes this one
rather than writing the same literal into every construction.
"""

from pyct.results.record import Environment

ENVIRONMENT = Environment(python="3.12.0", cvc5="1.2.1", platform="Test-1.0-arm64")
