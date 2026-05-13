from __future__ import annotations


def test_module_exports() -> None:
    from pyct.contracts import EMPTY_CONTRACTS, Contract, ContractSet, discover_contracts

    assert Contract is not None
    assert ContractSet is not None
    assert EMPTY_CONTRACTS is not None
    assert callable(discover_contracts)
    assert isinstance(EMPTY_CONTRACTS, ContractSet)
    assert EMPTY_CONTRACTS.requires == ()
    assert EMPTY_CONTRACTS.ensures == ()
