"""A loss site's code read from its file: the node whose kind fits the recorded downgrade, and
the name of each value going in, in the order the loss run records them."""

from pathlib import Path

import pytest

from pyct.core.foundation.branch import LossKind, Site
from pyct.results.losses import LossCode, loss_code

CODE = """\
import re


def f(data, i, c, p, s, bit, n):
    t = data[i] >> 4
    t = ord(c) >> 4
    t = re.compile(p).findall(s)
    flags = 1
    flags |= bit
    x = 3
    x <<= n
    return n >> 2
"""


@pytest.fixture
def file(tmp_path: Path) -> str:
    path = tmp_path / "losses_here.py"
    path.write_text(CODE)
    return str(path)


@pytest.mark.parametrize(
    ("at", "downgrade", "expected"),
    [
        pytest.param(
            (5, 8),
            ("__rshift__", LossKind.OPERATION, 2),
            LossCode("data[i] >> 4", (5, 5), ("arg1", None)),
            id="an element shifted",
        ),
        pytest.param(
            (6, 8),
            ("__rshift__", LossKind.OPERATION, 2),
            LossCode("ord(c) >> 4", (6, 6), ("arg1", None)),
            id="a call's answer shifted",
        ),
        pytest.param(
            (7, 8),
            ("re.compile(p).findall", LossKind.CALL, 1),
            LossCode("re.compile(p).findall(s)", (7, 7), ("s",)),
            id="a call on a call",
        ),
        pytest.param(
            (5, 8),
            ("__getitem__", LossKind.OPERATION, 2),
            LossCode("data[i]", (5, 5), ("data", "i")),
            id="an element",
        ),
        pytest.param(
            (12, 11),
            ("__rshift__", LossKind.OPERATION, 2),
            LossCode("n >> 2", (12, 12), ("n", None)),
            id="a name shifted",
        ),
    ],
)
def test_the_site_s_node_is_the_one_its_downgrade_names(
    file: str, at: tuple[int, int], downgrade: tuple[str, LossKind, int], expected: LossCode
) -> None:
    assert loss_code(Site(file, *at), *downgrade) == expected


def test_a_site_no_node_fits_names_each_value_by_its_position(file: str) -> None:
    code = loss_code(Site(file, 6, 8), "__add__", LossKind.OPERATION, 2)

    assert code == LossCode("__add__", (6, 6), ("arg1", "arg2"))
