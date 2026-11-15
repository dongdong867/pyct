"""The page on which the command's process names its import and its input's process."""

import pytest

from pyct.run.watch_page import WatchPage

MODULE = "some.module"
ARGV = ["run", f"{MODULE}::f", '{"x": 1}']


def test_the_page_names_the_module_only_while_it_imports() -> None:
    watch = WatchPage.for_command_line(ARGV)

    assert watch.module() is None
    with pytest.raises(RuntimeError), watch.importing(MODULE):
        assert watch.module() == MODULE
        raise RuntimeError("the import raised")
    assert watch.module() is None


@pytest.mark.parametrize(
    "module",
    [
        pytest.param("m" * 20_000, id="longer-than-a-page"),
        pytest.param("modulé.ünïcode", id="more-bytes-than-characters"),
    ],
)
def test_the_page_holds_any_module_the_command_line_gives(module: str) -> None:
    watch = WatchPage.for_command_line(["run", f"{module}::f"])

    with watch.importing(module):
        assert watch.module() == module


def test_the_page_names_the_input_s_process_beside_the_import() -> None:
    watch = WatchPage.for_command_line(ARGV)

    assert watch.input() is None
    with watch.importing(MODULE):
        watch.name_input(4321)
        assert watch.input() == 4321
        assert watch.module() == MODULE
    assert watch.input() == 4321
    watch.name_input(0)
    assert watch.input() is None
