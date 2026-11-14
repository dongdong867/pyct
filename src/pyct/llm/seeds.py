"""The seeds tool: the request text a seeds ask sends, and its reply read as seeds.

It implements ``pyct.run.llm_seeds.SeedProvider`` on top of ``Connection.ask``.
"""

from __future__ import annotations

from pyct.config.llm import SEEDS_TOOL
from pyct.llm.connection import Connection
from pyct.llm.replies import json_items
from pyct.llm.tool import Tool
from pyct.results.llm_asks import Unanswered
from pyct.run.llm_seeds import MOST_SEEDS, SeedReply, SeedRequest

SEEDS = Tool(SEEDS_TOOL, 4000)

# how one seed is written, which a later tool's request quotes word for word
SEED_FORM = (
    "A seed is a JSON object with one key per parameter of the signature, each holding that"
    " argument as JSON. A method's self is a JSON object of its class's constructor arguments,"
    " one key per constructor parameter. An argument the code uses as an object of a class is a"
    ' JSON object holding "__class__": "module::QualifiedName" and one key per constructor'
    " parameter; such an object may sit inside a list or dict, or be a constructor argument of"
    " another such object or of a method's self. Any other JSON object stays a dict."
    ' A dict the code uses as a dict, at any depth, writes a key "__class__" it holds as'
    ' "!__class__". pyct builds only the classes of the user\'s own code. An argument may take'
    " a type its annotation does not name, when the code shows it uses one."
)

# the reason a reply with no seeds pyct can read is ignored
NO_ARRAY = "no JSON array pyct can read in the reply"


class LlmSeeds:
    """Asks the connection for seeds and reads the reply's array, one item per seed."""

    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def seeds(self, request: SeedRequest) -> SeedReply | Unanswered:
        answer = self.connection.ask(SEEDS, request.place, request_text(request))
        if isinstance(answer, Unanswered):
            return answer
        items = json_items(answer.text)
        if items is None:
            return SeedReply((), answer.cost, ignored=NO_ARRAY)
        return SeedReply(items, answer.cost)


def request_text(request: SeedRequest) -> str:
    """The exact text a seeds ask sends: what the seeds are for, the target, its code, the
    classes of its folder and the user's seeds when there are any, the seed form, and the
    answer's form."""
    parts = [
        "pyct tests one Python function by running it on starting inputs, called seeds, then on"
        " inputs a solver finds by flipping the branches each input took. Suggest seeds that"
        " reach code the solver alone would struggle to reach.",
        f"Goal: {request.goal.value}. Together the seeds should run as many lines and branches"
        " of the function as they can.",
        f"Function: {request.place}\nSignature: {request.signature}",
        "The function's code, then the code of the functions it calls in its package:\n"
        f"```python\n{request.code}\n```",
    ]
    if request.classes:
        parts.append(
            "The classes of the function's folder, each under a heading that writes its name as"
            f' a seed\'s "__class__" writes it:\n```python\n{request.classes}\n```'
        )
    if request.seeds:
        quoted = "\n".join(request.seeds)
        parts.append(f"The user's seeds, which already run, one per line:\n{quoted}")
    parts.append(SEED_FORM)
    parts.append(
        f"Answer with a JSON array of at most {MOST_SEEDS} seed objects, and nothing else."
    )
    return "\n\n".join(parts)
