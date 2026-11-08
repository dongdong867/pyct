import inspect

from pyct.cli import missing_args_message


def test_missing_args_message_names_the_parameters_and_each_form() -> None:
    def target(x: int, name: str) -> None:
        pass

    message = missing_args_message(inspect.signature(target))

    assert "required" in message
    assert "x, name" in message
    assert "--args" in message
    assert "--seeds" in message
    assert "MODULE::FUNCTION JSON" in message
