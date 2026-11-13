"""Acceptance tests for run-a-plain-dict-stays-a-dict: the LLM's seeds and recorded replies.

The ``pyct run`` cases point the provider's base URLs at the stub on localhost, or replay a
recording against a closed port; the ``run()`` case answers with a fake ``SeedProvider``.
"""

import json
from pathlib import Path

from pyct.llm.seeds import request_text
from pyct.run.helpers import Helpers
from pyct.run.isolation import Isolation
from pyct.run.llm_seeds import SeedReply
from pyct.run.run import run
from pyct.run.setup import Setup
from pyct.run.target import load_target
from targets.dicts import class_key
from tests.acceptance.fake_seeds import COST, FakeSeeds
from tests.acceptance.harness import input_lines
from tests.acceptance.llm_stub import Stub, closed_port, llm_run, write_recording
from tests.acceptance.test_keep_a_tracked_dict_from_becoming_an_object_form import (
    HAS_CLASS,
    M,
    covers,
    line_of,
    returns_1,
    took,
)

ESCAPED = {"d": {"!__class__": 1}}
# the seed form the request had before this ticket, which the ticket's one sentence extends
BEFORE_SEED_FORM = (
    "A seed is a JSON object with one key per parameter of the signature, each holding that"
    " argument as JSON. A method's self is a JSON object of its class's constructor arguments,"
    " one key per constructor parameter. An argument the code uses as an object of a class is a"
    ' JSON object holding "__class__": "module::QualifiedName" and one key per constructor'
    " parameter; such an object may sit inside a list or dict, or be a constructor argument of"
    " another such object or of a method's self. Any other JSON object stays a dict. pyct"
    " builds only the classes of the user's own code. An argument may take a type its"
    " annotation does not name, when the code shows it uses one."
)
ESCAPE_SENTENCE = ' A dict that holds the key "__class__" writes it "!__class__".'
# a recording pyct wrote at 2e3ac4fa, before this ticket, for a run of kind_of whose seeds
# reply builds a Box, then gives a dict holding "__complex__"
OLD_RECORDING = (
    '{"pyct_llm_recording": 1, "provider": "openai", "model": "gpt-6-luna", "tools": '
    '["seeds"]}\n'
    '{"tool": "seeds", "place": "targets.dicts.class_key::kind_of", "try": 1, "reques'
    't": "pyct tests one Python function by running it on starting inputs, called see'
    "ds, then on inputs a solver finds by flipping the branches each input took. Sugg"
    "est seeds that reach code the solver alone would struggle to reach.\\n\\nGoal: cov"
    "erage. Together the seeds should run as many lines and branches of the function "
    "as they can.\\n\\nFunction: targets.dicts.class_key::kind_of\\nSignature: (d)\\n\\nTh"
    "e function's code, then the code of the functions it calls in its package:\\n```p"
    "ython\\n# targets.dicts.class_key.kind_of\\ndef kind_of(d):\\n    if isinstance(d, "
    "Box):\\n        return 1\\n    return 0\\n```\\n\\nThe classes of the function's fold"
    'er, each under a heading that writes its name as a seed\'s \\"__class__\\" writes i'
    "t:\\n```python\\n# targets.dicts.class_key::Box\\nclass Box:\\n    def __init__(self"
    ", d):\\n        self.d = d\\n\\n# targets.dicts.class_key::Holder\\nclass Holder:\\n "
    "   def __init__(self, d):\\n        self.d = d\\n\\n# targets.dicts.int_equal_keys:"
    ":Color\\nclass Color(enum.IntEnum):\\n\\n# targets.dicts.int_equal_keys::OwnHash\\nc"
    "lass OwnHash(int):\\n\\n# targets.dicts.int_equal_numbers::Level\\nclass Level(enum"
    ".IntEnum):\\n\\n# targets.dicts.int_equal_numbers::Rate\\nclass Rate(float):\\n\\n# t"
    "argets.dicts.walk_keys::Key\\n@dataclass(frozen=True)\\nclass Key:\\n    name: str\\"
    "n```\\n\\nA seed is a JSON object with one key per parameter of the signature, eac"
    "h holding that argument as JSON. A method's self is a JSON object of its class's"
    " constructor arguments, one key per constructor parameter. An argument the code "
    'uses as an object of a class is a JSON object holding \\"__class__\\": \\"module::Q'
    'ualifiedName\\" and one key per constructor parameter; such an object may sit ins'
    "ide a list or dict, or be a constructor argument of another such object or of a "
    "method's self. Any other JSON object stays a dict. pyct builds only the classes "
    "of the user's own code. An argument may take a type its annotation does not name"
    ", when the code shows it uses one.\\n\\nAnswer with a JSON array of at most 5 seed"
    ' objects, and nothing else.", "reply": "[{\\"d\\": {\\"__class__\\": \\"targets.dicts'
    '.class_key::Box\\", \\"d\\": {}}}, {\\"d\\": {\\"__complex__\\": true}}]", "tokens": {"'
    'in": 120, "out": 30}, "seconds": 1.459}\n'
)


def first_escaped(stdout: str) -> None:
    """The first line ran the escaped seed from the LLM, as a dict holding "__class__"."""
    first = input_lines(stdout)[0]
    assert (first["args"], first["source"], first["failure"]) == (ESCAPED, "llm_seed", None)
    assert took(first, HAS_CLASS) is True


# run-a-plain-dict-stays-a-dict-from-an-llm-seed
def test_from_an_llm_seed(stub: Stub, tmp_path: Path) -> None:
    stub.reply = json.dumps([ESCAPED])

    result = llm_run(stub.port, tmp_path, "--llm", "seeds", target=f"{M}::has_class")

    assert result.returncode == 0, result.stderr
    first_escaped(result.stdout)


# run-a-plain-dict-stays-a-dict-from-a-replayed-reply
def test_from_a_replayed_reply(tmp_path: Path) -> None:
    place = f"{M}::has_class"
    recording = write_recording(
        tmp_path / "recorded.jsonl", [{"place": place, "reply": json.dumps([ESCAPED])}]
    )

    result = llm_run(
        closed_port(), tmp_path, "--llm", "seeds", "--llm-replay", str(recording), target=place
    )

    assert result.returncode == 0, result.stderr
    first_escaped(result.stdout)


# run-a-plain-dict-stays-a-dict-replays-an-old-recording-as-before
def test_replays_an_old_recording_as_before(tmp_path: Path) -> None:
    recording = tmp_path / "old.jsonl"
    recording.write_text(OLD_RECORDING)
    place = f"{M}::kind_of"

    result = llm_run(
        closed_port(), tmp_path, "--llm", "seeds", "--llm-replay", str(recording), target=place
    )

    assert result.returncode == 0, result.stderr
    built, plain = input_lines(result.stdout)[:2]
    assert (built["source"], plain["source"]) == ("llm_seed", "llm_seed")
    assert (built["failure"], plain["failure"]) == (None, None)
    assert covers(built, returns_1(class_key.kind_of))
    assert covers(plain, line_of(class_key.kind_of, "return 0"))


# run-a-plain-dict-stays-a-dict-the-request-shows-the-escape
def test_the_request_shows_the_escape() -> None:
    provider = FakeSeeds(SeedReply((json.dumps({"d": {}}),), COST))
    setup = Setup(isolation=Isolation.IN_PROCESS, helpers=Helpers(seeds=provider))

    run(load_target(f"{M}::has_class"), [], setup=setup)

    [request] = provider.requests
    text = request_text(request)
    assert ESCAPE_SENTENCE in text
    assert BEFORE_SEED_FORM in text.replace(ESCAPE_SENTENCE, "", 1)
