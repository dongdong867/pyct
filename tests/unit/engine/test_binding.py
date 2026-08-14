"""Unit tests for the argument binding table.

The binding table is the map between SMT variable names and the
primitive leaves buried inside an argument. It is built once from the
seed arguments and then used three ways: to declare variables to the
solver, to name leaves when wrapping, and to write a solver model back
into a nested structure.
"""

import threading
from dataclasses import FrozenInstanceError, dataclass

import pytest

from pyct.engine.binding import (
    Leaf,
    Segment,
    apply_model,
    binding_var_types,
    build_binding,
    wrap_leaves,
)


def _by_route(binding: tuple[Leaf, ...]) -> dict[tuple, Leaf]:
    """Index leaves by their route's (kind, value) pairs for assertions."""
    return {tuple((s.kind, s.value) for s in leaf.route): leaf for leaf in binding}


class TestBuildBinding:
    """Walking arguments into leaves."""

    def test_top_level_primitive_keeps_legacy_var_name(self):
        binding = build_binding({"x": 5, "name": "a"})

        assert {leaf.var for leaf in binding} == {"x_VAR", "name_VAR"}
        assert all(leaf.route == () for leaf in binding)

    def test_sorts_map_python_types_to_smt(self):
        binding = build_binding({"b": True, "i": 1, "f": 1.5, "s": "x"})

        assert {leaf.param: leaf.sort for leaf in binding} == {
            "b": "Bool",
            "i": "Int",
            "f": "Real",
            "s": "String",
        }

    def test_bool_is_not_misread_as_int(self):
        """bool subclasses int, so ordering in the sort lookup matters."""
        binding = build_binding({"flag": True})

        assert binding[0].sort == "Bool"

    def test_nested_dict_produces_key_segments(self):
        binding = build_binding({"cfg": {"server": {"port": 80}}})

        assert len(binding) == 1
        assert binding[0].param == "cfg"
        assert binding[0].route == (Segment("key", "server"), Segment("key", "port"))
        assert binding[0].sort == "Int"

    def test_list_elements_get_distinct_variable_names(self):
        binding = build_binding({"items": [1, 2, 3]})

        assert len({leaf.var for leaf in binding}) == 3
        routes = _by_route(binding)
        assert set(routes) == {(("index", 0),), (("index", 1),), (("index", 2),)}

    def test_object_attributes_produce_attr_segments(self):
        class Rule:
            def __init__(self):
                self.limit = 10

        binding = build_binding({"rule": Rule()})

        assert binding[0].route == (Segment("attr", "limit"),)
        assert binding[0].sort == "Int"

    def test_frozen_dataclass_attributes_are_reachable(self):
        @dataclass(frozen=True)
        class Frozen:
            limit: int = 3

        binding = build_binding({"f": Frozen()})

        assert binding[0].route == (Segment("attr", "limit"),)

    def test_slotted_object_attributes_are_reachable(self):
        class Slotted:
            __slots__ = ("limit",)

            def __init__(self):
                self.limit = 3

        binding = build_binding({"s": Slotted()})

        assert binding[0].route == (Segment("attr", "limit"),)

    def test_mixed_container_kinds_in_one_route(self):
        class Limits:
            def __init__(self):
                self.retries = 3

        binding = build_binding({"cfg": {"ports": [80], "limits": Limits()}})
        routes = _by_route(binding)

        assert (("key", "ports"), ("index", 0)) in routes
        assert (("key", "limits"), ("attr", "retries")) in routes

    def test_variable_names_are_unique(self):
        binding = build_binding(
            {"a": {"b": {"c": 1}, "d": [2, 3]}, "e": 4},
        )

        names = [leaf.var for leaf in binding]
        assert len(names) == len(set(names))

    def test_none_leaves_produce_no_variable(self):
        """None has no SMT sort, so it is left concrete."""
        binding = build_binding({"cfg": {"opt": None, "port": 80}})

        assert len(binding) == 1
        assert binding[0].route == (Segment("key", "port"),)

    def test_unsupported_leaf_types_are_skipped(self):
        binding = build_binding({"cfg": {"blob": b"bytes", "port": 80}})

        assert [leaf.route for leaf in binding] == [(Segment("key", "port"),)]

    def test_empty_containers_produce_no_leaves(self):
        assert build_binding({"a": {}, "b": []}) == ()

    def test_self_referencing_structure_terminates(self):
        cyclic: dict = {"n": 1}
        cyclic["self"] = cyclic

        binding = build_binding({"c": cyclic})

        assert [leaf.route for leaf in binding] == [(Segment("key", "n"),)]

    def test_uncopyable_parameter_contributes_no_leaves(self):
        """A parameter that cannot be copied is left fully concrete."""
        binding = build_binding({"cfg": {"port": 80, "lock": threading.Lock()}})

        assert binding == ()

    def test_uncopyable_parameter_does_not_disable_the_others(self):
        binding = build_binding({"conn": threading.Lock(), "cfg": {"port": 80}})

        assert [leaf.param for leaf in binding] == ["cfg"]


class TestModelKey:
    """The name a variable carries once solver output has been parsed."""

    def test_strips_the_var_suffix_from_a_top_level_parameter(self):
        binding = build_binding({"x": 1})

        assert binding[0].var == "x_VAR"
        assert binding[0].model_key == "x"

    def test_strips_the_var_suffix_from_a_nested_leaf(self):
        binding = build_binding({"cfg": {"port": 80}})

        assert binding[0].var.endswith("_VAR")
        assert binding[0].model_key == binding[0].var[: -len("_VAR")]

    def test_model_keys_stay_unique_after_stripping(self):
        binding = build_binding({"a": {"b": 1, "c": 2}, "d": 3})

        keys = [leaf.model_key for leaf in binding]
        assert len(keys) == len(set(keys))


class TestBindingVarTypes:
    """The mapping handed to the solver."""

    def test_maps_every_variable_to_its_sort(self):
        binding = build_binding({"cfg": {"port": 80, "host": "h"}})

        var_types = binding_var_types(binding)

        assert set(var_types.values()) == {"Int", "String"}
        assert set(var_types) == {leaf.var for leaf in binding}

    def test_empty_binding_yields_empty_mapping(self):
        assert binding_var_types(()) == {}


class TestApplyModel:
    """Writing a solver model back into nested arguments."""

    def test_writes_nested_dict_value(self):
        args = {"cfg": {"server": {"port": 80}}}
        binding = build_binding(args)

        out = apply_model(args, binding, {binding[0].model_key: 8080})

        assert out["cfg"]["server"]["port"] == 8080

    def test_leaves_the_original_arguments_untouched(self):
        args = {"cfg": {"server": {"port": 80}}}
        binding = build_binding(args)

        apply_model(args, binding, {binding[0].model_key: 8080})

        assert args["cfg"]["server"]["port"] == 80

    def test_partial_model_keeps_unmentioned_values(self):
        args = {"cfg": {"port": 80, "host": "h"}}
        binding = build_binding(args)
        port = next(leaf for leaf in binding if leaf.route[-1].value == "port")

        out = apply_model(args, binding, {port.model_key: 9090})

        assert out["cfg"] == {"port": 9090, "host": "h"}

    def test_writes_list_elements_independently(self):
        args = {"items": [1, 2]}
        binding = build_binding(args)
        model = {leaf.model_key: 10 * (leaf.route[0].value + 1) for leaf in binding}

        assert apply_model(args, binding, model)["items"] == [10, 20]

    def test_writes_object_attribute(self):
        class Rule:
            def __init__(self):
                self.limit = 1

        args = {"rule": Rule()}
        binding = build_binding(args)

        out = apply_model(args, binding, {binding[0].model_key: 42})

        assert out["rule"].limit == 42
        assert args["rule"].limit == 1

    def test_writes_frozen_dataclass_attribute(self):
        @dataclass(frozen=True)
        class Frozen:
            limit: int = 1

        args = {"f": Frozen()}
        binding = build_binding(args)

        assert apply_model(args, binding, {binding[0].model_key: 7})["f"].limit == 7

    def test_top_level_primitive_is_replaced(self):
        args = {"x": 1}
        binding = build_binding(args)

        assert apply_model(args, binding, {"x": 99}) == {"x": 99}

    def test_declared_variable_name_is_not_a_model_key(self):
        """The parser strips ``_VAR``; looking up by ``var`` finds nothing."""
        args = {"cfg": {"port": 80}}
        binding = build_binding(args)

        out = apply_model(args, binding, {binding[0].var: 8080})

        assert out["cfg"]["port"] == 80

    def test_unknown_model_keys_are_ignored(self):
        args = {"cfg": {"port": 80}}
        binding = build_binding(args)

        assert apply_model(args, binding, {"nonexistent": 5})["cfg"]["port"] == 80

    def test_parameters_without_leaves_pass_through_by_reference(self):
        lock = threading.Lock()
        args = {"conn": lock, "cfg": {"port": 80}}
        binding = build_binding(args)

        out = apply_model(args, binding, {binding[0].model_key: 8080})

        assert out["conn"] is lock
        assert out["cfg"]["port"] == 8080


class TestWrapLeaves:
    """Naming leaves so branch conditions become symbolic.

    These tests need a real engine reference: ``Concolic`` silently
    discards the expression when ``engine`` is None, so an engine-less
    wrap would leave every leaf carrying its concrete value and the
    name assertions would pass for the wrong reason.
    """

    def test_nested_leaf_becomes_concolic_with_its_variable_name(self, engine):
        args = {"cfg": {"port": 80}}
        binding = build_binding(args)

        wrapped = wrap_leaves(args, binding, engine)
        leaf_value = wrapped["cfg"]["port"]

        assert type(leaf_value).__name__ == "ConcolicInt"
        assert leaf_value.expr == binding[0].var

    def test_wrapping_does_not_mutate_the_original(self, engine):
        args = {"cfg": {"port": 80}}
        binding = build_binding(args)

        wrap_leaves(args, binding, engine)

        assert type(args["cfg"]["port"]).__name__ == "int"

    def test_list_elements_receive_distinct_names(self, engine):
        args = {"items": [7, 7]}
        binding = build_binding(args)

        wrapped = wrap_leaves(args, binding, engine)

        assert wrapped["items"][0].expr != wrapped["items"][1].expr

    def test_object_attribute_is_wrapped(self, engine):
        class Rule:
            def __init__(self):
                self.limit = 1

        args = {"rule": Rule()}
        binding = build_binding(args)

        wrapped = wrap_leaves(args, binding, engine)

        assert type(wrapped["rule"].limit).__name__ == "ConcolicInt"
        assert type(args["rule"].limit).__name__ == "int"

    def test_values_without_leaves_are_passed_through(self, engine):
        lock = threading.Lock()
        args = {"conn": lock}

        assert wrap_leaves(args, (), engine)["conn"] is lock


class TestSegmentAndLeaf:
    """Value-object guarantees the engine relies on."""

    def test_segment_is_frozen(self):
        with pytest.raises(FrozenInstanceError):
            Segment("key", "a").value = "b"  # type: ignore[misc]

    def test_leaf_is_frozen(self):
        leaf = Leaf(var="v", param="p", route=(), sort="Int")
        with pytest.raises(FrozenInstanceError):
            leaf.var = "other"  # type: ignore[misc]
