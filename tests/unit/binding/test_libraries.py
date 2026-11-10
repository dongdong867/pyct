"""A class is a library's when Python's standard library or an installed distribution holds
it, unless the code whose hint names it is in the same top-level package."""

import array
import collections
import datetime
import types

import pluggy
import pytest

from pyct.binding.libraries import from_a_library
from tests.unit.binding.hint_classes import Box, Coord, Pair, Spot
from tests.unit.binding.named_classes import Point


def target() -> None:
    """A function of the user's own code, a hint's owner."""


@pytest.mark.parametrize(
    "cls",
    [
        int,
        dict,
        types.ModuleType,
        collections.deque,
        array.array,
        datetime.date,
        pluggy.PluginManager,
    ],
)
def test_a_standard_library_or_installed_class_is_a_library_s(cls: type) -> None:
    assert from_a_library(cls)
    assert from_a_library(cls, target)


@pytest.mark.parametrize("cls", [Point, Spot, Coord, Pair, Box])
def test_a_class_of_the_user_s_own_code_is_not_a_library_s(cls: type) -> None:
    assert not from_a_library(cls)
    assert not from_a_library(cls, target)


def test_a_library_s_class_is_its_own_under_a_hint_the_same_package_writes() -> None:
    assert not from_a_library(pluggy.PluginManager, pluggy.HookimplMarker)
    assert not from_a_library(collections.deque, collections.OrderedDict)


def test_a_class_whose_module_has_no_file_is_read_by_its_module_s_name() -> None:
    assert not from_a_library(type("Made", (), {"__module__": "no_such_module_here"}))
    assert from_a_library(type("Made", (), {"__module__": "itertools"}))
