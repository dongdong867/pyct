import sys
import types

import pytest

from pyct.execution.line_events import listen, listening, unused_tool_id


def held_tools() -> list[int]:
    return [tool for tool in range(6) if sys.monitoring.get_tool(tool) is not None]


def test_unused_tool_id_takes_an_unassigned_id() -> None:
    if sys.monitoring.get_tool(3) is not None:
        pytest.skip("tool id 3 is already held")

    assert unused_tool_id() == 3


def test_unused_tool_id_falls_back_to_a_reserved_id() -> None:
    for tool_id in (3, 4, 0):
        if sys.monitoring.get_tool(tool_id) is not None:
            pytest.skip(f"tool id {tool_id} is already held")
    sys.monitoring.use_tool_id(3, "test")
    sys.monitoring.use_tool_id(4, "test")
    try:
        assert unused_tool_id() == 0
    finally:
        sys.monitoring.free_tool_id(3)
        sys.monitoring.free_tool_id(4)


def test_listening_hands_each_line_to_the_callback_inside_the_block() -> None:
    seen: list[int] = []

    def on_line(code: types.CodeType, line: int) -> object:
        if code.co_filename == __file__:
            seen.append(line)
        return None

    before = held_tools()
    with listening(on_line):
        start = sys._getframe().f_lineno
    after = sys._getframe().f_lineno

    assert start in seen
    assert after not in seen
    assert held_tools() == before


def test_listening_gives_its_tool_back_when_the_block_raises() -> None:
    before = held_tools()

    with pytest.raises(ValueError, match="inside"), listening(lambda _code, _line: None):
        raise ValueError("inside")

    assert held_tools() == before


def test_listen_gives_its_tool_back_when_its_callback_cannot_be_registered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monitoring = sys.monitoring
    register = monitoring.register_callback
    before = held_tools()

    def refuse(tool_id: int, event: int, callback: object) -> object:
        # the teardown's own call, which takes the callback away, goes through
        if callback is not None:
            raise ValueError("cannot register the callback")
        return register(tool_id, event, None)

    with monkeypatch.context() as patched:
        patched.setattr(monitoring, "register_callback", refuse)
        with pytest.raises(ValueError, match="cannot register the callback"):
            listen(lambda _code, _line: None)

    assert held_tools() == before


def test_listening_hands_each_branch_to_its_callback() -> None:
    went: list[tuple[int, int]] = []

    def on_branch(code: types.CodeType, test: int, target: int) -> object:
        if code.co_filename == __file__:
            went.append((test, target))
        return None

    before = held_tools()
    with listening(lambda _code, _line: None, on_branch):
        for _ in range(2):
            pass
    after = list(went)
    for _ in range(2):
        pass

    # the loop's test went into its body twice and past it once
    assert len(after) == 3
    assert went == after
    assert held_tools() == before
