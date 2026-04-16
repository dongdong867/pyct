"""Transaction ledger analysis benchmark target.

Category: Complex structures — list-of-dicts processing with running state
Intent: Analyze a ledger of transaction dicts, tracking running balance and detecting anomalies
Challenge: The solver must construct a list of dicts with specific field values and orderings.
    Anomaly detection depends on cumulative state (running balance, consecutive amounts),
    so the solver must reason about how earlier list elements affect later branch conditions.
"""

from __future__ import annotations


def _has_valid_structure(txn: dict) -> bool:
    """Check whether a transaction dict has the required fields and valid types."""
    if "amount" not in txn or "type" not in txn:
        return False
    if not isinstance(txn["amount"], (int, float)):
        return False
    if txn["type"] not in ("credit", "debit"):
        return False
    return True


def _classify_transaction_mix(transactions: list) -> str:
    """Return whether the ledger is all credits, all debits, or mixed."""
    types = {txn["type"] for txn in transactions}
    if types == {"credit"}:
        return "all_credits"
    if types == {"debit"}:
        return "all_debits"
    return "mixed"


def _detect_anomalies(transactions: list) -> str | None:
    """Return the first anomaly classification found, or None."""
    balance = 0
    prev_amount = None

    for txn in transactions:
        amount = txn["amount"]
        if amount < 0:
            return "contains_negative"
        if amount > 10000:
            return "large_transaction_detected"

        if txn["type"] == "credit":
            balance += amount
        else:
            balance -= amount

        if balance < 0:
            return "overdraft_detected"
        if prev_amount is not None and amount == prev_amount:
            return "duplicate_detected"
        prev_amount = amount

    return None


def _classify_final_balance(transactions: list) -> str:
    """Classify the ledger by its final balance."""
    balance = 0
    for txn in transactions:
        if txn["type"] == "credit":
            balance += txn["amount"]
        else:
            balance -= txn["amount"]

    if balance > 0:
        return "positive_balance"
    if balance == 0:
        return "zero_balance"
    return "negative_balance"


def transaction_ledger_analysis(transactions: list) -> str:
    """Process a list of transaction dicts and return a string classification."""
    if len(transactions) == 0:
        return "empty_ledger"

    for txn in transactions:
        if not _has_valid_structure(txn):
            return "invalid_transaction"

    if len(transactions) < 3:
        return "insufficient_data"

    mix = _classify_transaction_mix(transactions)

    anomaly = _detect_anomalies(transactions)
    if anomaly is not None:
        return anomaly

    return mix + "_" + _classify_final_balance(transactions)
