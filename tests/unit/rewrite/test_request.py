"""A request writes the condition and the path's earlier conditions as Python writes them, and the
input's values as JSON, or as Python writes them when JSON cannot hold them, each cut."""

from pathlib import Path

from pyct.binding.bind import Seed
from pyct.branches.plan import plan
from pyct.core.foundation.branch import Branch, Site
from pyct.results.causes import Condition
from pyct.results.record import MissWhy
from pyct.rewrite.ask import GivenUp
from pyct.rewrite.request import EARLIER, VALUE_SIZE, About, condition_text, request_for

ABOUT = About("m:2:7", "code", {"nowhere.py": "nowhere"})


def test_the_condition_is_the_outermost_expression_at_its_site_an_and_aside(tmp_path: Path) -> None:
    file = tmp_path / "m.py"
    file.write_text(
        'def f(s, n):\n    if s.startswith("-") and float(s) == 1.5:\n        return 1\n'
    )

    assert condition_text(Site(str(file), 2, 7), "m") == 's.startswith("-")'
    assert condition_text(Site(str(file), 2, 29), "m") == "float(s) == 1.5"


def test_a_site_whose_file_does_not_read_is_written_out_by_its_module(tmp_path: Path) -> None:
    missing = str(tmp_path / "gone.py")

    assert condition_text(Site(missing, 2, 7), "pkg.gone") == "the condition at pkg.gone:2:7"


def test_each_condition_is_named_by_the_module_about_gives_its_file(tmp_path: Path) -> None:
    first = Branch(["<", "n", 1], True, Site(str(tmp_path / "a.py"), 3, 4))
    second = Branch(["<", "n", 2], True, Site(str(tmp_path / "b.py"), 5, 6))
    aimed = Branch([">", "n", 0], False, Site(str(tmp_path / "c.py"), 7, 8))
    wanted = plan((first, second, aimed))
    assert wanted is not None
    given = GivenUp(Condition(aimed.site, True), wanted, Seed.of({"n": 0}), MissWhy.UNKNOWN)
    modules = {str(tmp_path / f"{name}.py"): f"pkg.{name}" for name in "abc"}

    request = request_for(given, About("pkg.c:7:8", "code", modules), ())

    assert [each.text for each in request.earlier] == [
        "the condition at pkg.a:3:4",
        "the condition at pkg.b:5:6",
    ]
    assert request.condition.text == "the condition at pkg.c:7:8"
    assert str(tmp_path) not in repr(request)


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


def test_a_condition_the_path_took_early_and_again_near_the_aim_is_kept_at_its_last() -> None:
    guard = Branch(["<", "n", 1], True, Site("nowhere.py", 1, 4))
    between = [Branch(["<", "n", at], True, Site("nowhere.py", at, 4)) for at in range(2, 40)]
    aimed = Branch([">", "n", 0], False, Site("nowhere.py", 100, 4))
    wanted = plan((guard, *between, guard, aimed))
    assert wanted is not None
    given = GivenUp(Condition(aimed.site, True), wanted, Seed.of({"n": 0}), MissWhy.UNKNOWN)

    request = request_for(given, ABOUT, ())

    lines = [each.text.rpartition(":")[0].rpartition(":")[2] for each in request.earlier]
    # the guard, taken at the start and again just before the aim, is the nearest
    assert lines == [*(str(at) for at in range(40 - EARLIER + 1, 40)), "1"]


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
