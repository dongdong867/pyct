"""The page on which the command's process names the module it is importing."""

import pytest

from pyct.run.import_watch import ImportWatch

MODULE = "some.module"
ARGV = ["run", f"{MODULE}::f", '{"x": 1}']


def test_the_page_names_the_module_only_while_it_imports() -> None:
    watch = ImportWatch.for_command_line(ARGV)

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
    watch = ImportWatch.for_command_line(["run", f"{module}::f"])

    with watch.importing(module):
        assert watch.module() == module
