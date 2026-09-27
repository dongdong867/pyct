"""A module's substituted code, and whose a failure to make it is."""

import ast
from pathlib import Path

import pytest

from pyct.core.values import raised_by_target
from pyct.intercept import compiled
from pyct.intercept.compiled import SubstitutionError, substituted_code


def test_the_code_names_the_file_and_honors_its_encoding(tmp_path: Path) -> None:
    path = str(tmp_path / "latin.py")
    source = "# -*- coding: latin-1 -*-\nword = 'caf\xe9' in 'a caf\xe9'\n".encode("latin-1")

    code = substituted_code(source, path)

    assert code.co_filename == path
    assert "__pyct_in__" in code.co_names
    assert "café" in code.co_consts


@pytest.mark.parametrize(
    "source",
    [
        # refused by the parser, and by the compiler past it
        "def g(:\n    return 1\n",
        "x = 1\nnonlocal x\n",
    ],
)
def test_a_module_that_does_not_compile_raises_python_s_own_error_as_the_target_s(
    source: str,
) -> None:
    with pytest.raises(SyntaxError) as plain:
        compile(source, "broken.py", "exec")

    with pytest.raises(SyntaxError) as raised:
        substituted_code(source.encode(), "broken.py")

    assert (raised.value.msg, raised.value.lineno) == (plain.value.msg, plain.value.lineno)
    assert raised_by_target(raised.value)


def test_a_transform_that_fails_is_pyct_s(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(tree: ast.Module) -> ast.Module:
        raise ValueError("no")

    monkeypatch.setattr(compiled, "substitute", broken)

    with pytest.raises(SubstitutionError, match="cannot substitute m.py: ValueError") as raised:
        substituted_code(b"x = 1\n", "m.py")
    assert not raised_by_target(raised.value)


def test_a_substituted_tree_that_does_not_compile_where_the_source_does_is_pyct_s(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unplaced(tree: ast.Module) -> ast.Module:
        tree.body[0].lineno = 9  # pyrefly: ignore[missing-attribute]
        return tree

    monkeypatch.setattr(compiled, "substitute", unplaced)

    with pytest.raises(SubstitutionError, match="cannot substitute m.py: ValueError"):
        substituted_code(b"x = 1\n", "m.py")
