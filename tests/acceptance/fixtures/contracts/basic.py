"""Simple icontract-decorated targets for contract-discovery acceptance tests."""

from __future__ import annotations

import icontract


@icontract.require(lambda x: x > 0, description="x must be positive")
@icontract.ensure(lambda result, x: result == x * 2, description="result is x doubled")
def positive_double(x: int) -> int:
    return x * 2


def no_contracts(x: int) -> int:
    return x
