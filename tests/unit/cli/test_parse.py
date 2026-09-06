from pyct.cli import RunCommand, parse_command


def test_seed_may_follow_the_target() -> None:
    assert parse_command(["run", "m::f", '{"x": 1}']) == RunCommand(spec="m::f", seed_text='{"x": 1}')


def test_seed_may_come_through_the_args_flag() -> None:
    assert parse_command(["run", "m::f", "--args", '{"x": 1}']) == RunCommand(
        spec="m::f", seed_text='{"x": 1}'
    )


def test_seed_may_be_absent() -> None:
    assert parse_command(["run", "m::f"]) == RunCommand(spec="m::f", seed_text=None)
