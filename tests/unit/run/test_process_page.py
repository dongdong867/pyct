"""pyct's process names the input's process it runs on the watcher's page, for the guard."""

from collections.abc import Callable

import pytest

from pyct.run import process
from pyct.run.process import Child, watched
from pyct.run.watch_page import WatchPage
from tests.unit.run.test_process import sleeper


@pytest.fixture
def page(monkeypatch: pytest.MonkeyPatch) -> WatchPage:
    """A page pyct's process names its inputs on, and none again after the test."""
    monkeypatch.setattr(process, "_page", None)
    named = WatchPage.for_command_line([])
    process.name_inputs_on(named)
    return named


def reading(page: WatchPage, seen: list[int | None]) -> Callable[[], bool]:
    """A look that notes the input's process the page names, and never falls behind."""

    def look() -> bool:
        seen.append(page.input())
        return False

    return look


def test_the_page_names_the_input_s_process_while_pyct_holds_it(page: WatchPage) -> None:
    started: list[int] = []
    seen: list[int | None] = []

    def start() -> int:
        started.append(sleeper(0.2))
        return started[0]

    watched(start, None, reading(page, seen))

    assert seen
    assert set(seen) == set(started)
    assert page.input() is None


# a Ctrl-C held while pyct reaps the input's process goes on from the reap
def test_the_page_names_no_input_after_a_reap_that_raises(
    page: WatchPage, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_end = Child.end

    def end_then_interrupt(self: Child) -> None:
        real_end(self)
        raise KeyboardInterrupt

    monkeypatch.setattr(Child, "end", end_then_interrupt)
    with pytest.raises(KeyboardInterrupt):
        watched(lambda: sleeper(0), None)

    assert page.input() is None
