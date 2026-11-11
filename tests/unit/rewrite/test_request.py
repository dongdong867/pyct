"""A request writes the condition and the path's earlier conditions as Python writes them, and the
input's values as JSON, each cut."""

from pathlib import Path

from pyct.binding.bind import Seed
from pyct.branches.plan import plan
from pyct.core.foundation.branch import Branch, Site
from pyct.results.causes import Condition
from pyct.results.record import MissWhy
from pyct.rewrite.ask import GivenUp
from pyct.rewrite.request import EARLIER, VALUE_SIZE, About, condition_text, request_for

ABOUT = About("m:2:7", "m.py:2:7", "code")


def test_the_condition_is_the_outermost_expression_at_its_site_an_and_aside(tmp_path: Path) -> None:
    file = tmp_path / "m.py"
    file.write_text(
        'def f(s, n):\n    if s.startswith("-") and float(s) == 1.5:\n        return 1\n'
    )

    assert condition_text(Site(str(file), 2, 7)) == 's.startswith("-")'
    assert condition_text(Site(str(file), 2, 29)) == "float(s) == 1.5"


def test_a_site_whose_file_does_not_read_is_written_out(tmp_path: Path) -> None:
    missing = str(tmp_path / "gone.py")

    assert condition_text(Site(missing, 2, 7)) == f"the condition at {missing}:2:7"


def test_the_path_s_earlier_conditions_are_distinct_the_nearest_kept() -> None:
    forks = [Branch(["<", "n", at], True, Site("nowhere.py", at, 4)) for at in range(EARLIER + 5)]
    forks += [forks[-1], Branch(["isint", "s"], True, Site("nowhere.py", 99, 4), raising=True)]
    aimed = Branch([">", "n", 0], False, Site("nowhere.py", 100, 4))
    wanted = plan((*forks, aimed))
    assert wanted is not None
    given = GivenUp(Condition(aimed.site, True), wanted, Seed.of({"n": 0}), MissWhy.UNKNOWN)

    request = request_for(given, ABOUT, ())

    lines = [each.text.rpartition(":")[0].rpartition(":")[2] for each in request.earlier]
    assert lines == [str(at) for at in range(5, EARLIER + 5)]
    assert request.answer == "unknown"


def test_each_value_is_json_cut_or_python_s_words_for_one_json_cannot_write() -> None:
    aimed = Branch([">", "n", 0], False, Site("nowhere.py", 1, 4))
    wanted = plan((aimed,))
    assert wanted is not None
    origin = Seed.of({"n": 0, "s": "x" * (VALUE_SIZE * 2), "o": frozenset({1})})
    given = GivenUp(Condition(aimed.site, True), wanted, origin, MissWhy.TIMEOUT)

    args = dict(request_for(given, ABOUT, ()).args)

    assert args["n"] == "0"
    assert len(args["s"]) == VALUE_SIZE
    assert args["o"] == "frozenset({1})"
