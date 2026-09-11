from pyct.cli import RunCommand, parse_command


def test_seed_may_follow_the_target() -> None:
    assert parse_command(["run", "m::f", '{"x": 1}']) == RunCommand(
        spec="m::f", seed_text='{"x": 1}'
    )


def test_seed_may_come_through_the_args_flag() -> None:
    assert parse_command(["run", "m::f", "--args", '{"x": 1}']) == RunCommand(
        spec="m::f", seed_text='{"x": 1}'
    )


def test_seed_may_be_absent() -> None:
    assert parse_command(["run", "m::f"]) == RunCommand(spec="m::f", seed_text=None)


def test_the_budget_is_read_from_its_flag() -> None:
    assert parse_command(["run", "m::f", '{"x": 1}', "--budget", "1.5"]) == RunCommand(
        spec="m::f", seed_text='{"x": 1}', budget_text="1.5"
    )


def test_the_budget_may_be_absent() -> None:
    assert parse_command(["run", "m::f"]).budget_text is None
