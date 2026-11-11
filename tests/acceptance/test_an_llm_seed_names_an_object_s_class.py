"""Acceptance tests for an-llm-seed-names-an-object-s-class: the LLM's seeds build objects through
the classes the request lists, and a method's ``self`` through its constructor.

The ``run()`` cases answer with a fake ``SeedProvider``; the ``pyct run`` cases point the
provider's base URLs at the stub on localhost, or replay a recording against a closed port.
"""

import sys
from dataclasses import dataclass, field

import pytest

from pyct.llm.seeds import SEED_FORM, request_text
from pyct.run.helpers import Helpers
from pyct.run.isolation import Isolation
from pyct.run.llm_seeds import SeedReply, SeedRequest
from pyct.run.run import run
from pyct.run.setup import Setup
from pyct.run.target import load_target
from tests.acceptance.fake_seeds import COST, FakeSeeds

M = "targets.llm.shop.models"
GREET = "targets.llm.shop.greet"
CHECK = "targets.llm.plain.check::check"


@dataclass
class Watching(FakeSeeds):
    """A fake provider that also keeps, for each ask, whether ``M`` was imported by then."""

    imported: list[bool] = field(default_factory=list)

    def seeds(self, request: SeedRequest) -> SeedReply:
        self.imported.append(M in sys.modules)
        super().seeds(request)
        return SeedReply((), COST)


def asked(spec: str, seed: dict[str, object]) -> tuple[Watching, str]:
    """The provider a run of ``spec`` from ``seed`` asked, and the text its one request sends."""
    provider = Watching(SeedReply((), COST))
    setup = Setup(isolation=Isolation.IN_PROCESS, helpers=Helpers(seeds=provider))
    run(load_target(spec), [seed], setup=setup)
    [request] = provider.requests
    return provider, request_text(request)


# llm-seeds-name-a-class-the-request-shows-the-class
def test_the_request_shows_the_class_and_its_module_is_not_imported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delitem(sys.modules, M, raising=False)

    provider, text = asked(f"{GREET}::greet", {"c": 1})

    assert (
        f"# {M}::Customer\nclass Customer:\n    def __init__(self, name, age):\n"
        '        if age < 0:\n            raise ValueError("negative age")\n'
        "        self.name = name\n        self.age = age\n"
    ) in text
    assert '"__class__": "module::QualifiedName"' in text
    assert provider.imported == [False]


# llm-seeds-name-a-class-sends-no-class-list-when-the-folder-has-none
def test_the_request_has_no_classes_section_when_the_folder_defines_no_class() -> None:
    provider, text = asked(CHECK, {"n": 0})

    [request] = provider.requests
    assert request.classes == ""
    assert not [line for line in text.splitlines() if line.startswith("# ") and "::" in line]
    # the code's section, then the user's seed, then the seed form
    assert (
        f'```\n\nThe user\'s seeds, which already run, one per line:\n{{"n": 0}}\n\n{SEED_FORM}'
        in text
    )
    plain = SeedRequest(request.place, request.code, request.signature, request.seeds, request.goal)
    assert text == request_text(plain)


# llm-seeds-build-self-the-request-shows-self-s-constructor
def test_the_request_shows_self_s_constructor_and_how_self_is_written() -> None:
    _, text = asked(f"{M}::Till.total", {"self": {"owner": "x"}, "discount": 0})

    assert "def __init__(self, owner):\n    self.owner = owner" in text
    assert "A method's self is a JSON object of its class's constructor arguments" in text
