from __future__ import annotations

import icontract

from pyct.contracts import EMPTY_CONTRACTS, Contract, ContractSet, discover_contracts


def test_module_exports() -> None:
    assert Contract is not None
    assert ContractSet is not None
    assert EMPTY_CONTRACTS is not None
    assert callable(discover_contracts)
    assert isinstance(EMPTY_CONTRACTS, ContractSet)
    assert EMPTY_CONTRACTS.requires == ()
    assert EMPTY_CONTRACTS.ensures == ()


def test_discover_require_populates_requires() -> None:
    @icontract.require(lambda x: x > 0, description="x must be positive")
    def f(x: int) -> int:
        return x

    result = discover_contracts(f)
    assert len(result.requires) == 1
    assert result.ensures == ()
    contract = result.requires[0]
    assert callable(contract.predicate)
    assert contract.predicate(5) is True
    assert contract.predicate(-1) is False
    assert contract.description == "x must be positive"
    assert ":" in contract.source
    path, _, line = contract.source.rpartition(":")
    assert path.endswith("test_contracts.py")
    assert line.isdigit()


def test_discover_ensure_populates_ensures() -> None:
    @icontract.ensure(lambda result, x: result == x * 2)
    def g(x: int) -> int:
        return x * 2

    result = discover_contracts(g)
    assert result.requires == ()
    assert len(result.ensures) == 1
    contract = result.ensures[0]
    assert callable(contract.predicate)
    assert contract.description is None
    _, _, line = contract.source.rpartition(":")
    assert line.isdigit()


def test_discover_no_contracts_returns_empty() -> None:
    def h(x: int) -> int:
        return x

    result = discover_contracts(h)
    assert result.requires == ()
    assert result.ensures == ()


def test_discover_both_decorators_populate_both() -> None:
    @icontract.require(lambda x: x >= 0)
    @icontract.ensure(lambda result: result >= 0)
    def k(x: int) -> int:
        return x

    result = discover_contracts(k)
    assert len(result.requires) == 1
    assert len(result.ensures) == 1


def test_discover_requires_preserve_source_order() -> None:
    @icontract.require(lambda x: x > 0, description="A")
    @icontract.require(lambda x: x < 100, description="B")
    @icontract.require(lambda x: x != 50, description="C")
    def f(x: int) -> int:
        return x

    result = discover_contracts(f)
    assert [c.description for c in result.requires] == ["A", "B", "C"]


def test_discover_ensures_preserve_source_order() -> None:
    @icontract.ensure(lambda result: result >= 0, description="X")
    @icontract.ensure(lambda result: result < 1000, description="Y")
    @icontract.ensure(lambda result: result != 7, description="Z")
    def g(x: int) -> int:
        return x

    result = discover_contracts(g)
    assert [c.description for c in result.ensures] == ["X", "Y", "Z"]
