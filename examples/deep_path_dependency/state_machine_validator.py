"""State machine validator benchmark target.

Category: Deep path dependency — multi-step sequence validation
Intent: Validate a comma-separated event sequence against an order lifecycle state machine
Challenge: To reach deep branches like "completed_delivery", the solver must generate
    the exact 4-step sequence "create,pay,ship,deliver". Each transition is only valid
    from specific states, creating a chain of path dependencies that require the solver
    to reason about cumulative string structure, not just individual branch conditions.
"""

from __future__ import annotations

KNOWN_EVENTS = frozenset({"create", "pay", "ship", "deliver", "cancel", "refund"})

TERMINAL_STATES = frozenset({"deliver", "cancel", "refund"})

VALID_TRANSITIONS: dict[str, frozenset[str]] = {
    "create": frozenset({"pay", "cancel"}),
    "pay": frozenset({"ship", "refund"}),
    "ship": frozenset({"deliver"}),
}


def _classify_terminal(state: str) -> str:
    """Classify the outcome for a terminal state reached at end of sequence."""
    if state == "deliver":
        return "completed_delivery"
    if state == "cancel":
        return "cancelled_before_payment"
    return "refunded_after_payment"


def _walk_transitions(events: list[str]) -> str:
    """Walk the event sequence through the state machine, returning a classification."""
    state = events[0]

    for i in range(1, len(events)):
        event = events[i]
        if event not in KNOWN_EVENTS:
            return "unknown_event"
        allowed = VALID_TRANSITIONS.get(state)
        if allowed is None:
            return "events_after_terminal"
        if event not in allowed:
            return "invalid_transition_from_" + state
        state = event

    if state in TERMINAL_STATES:
        return _classify_terminal(state)
    return "incomplete_" + state


def state_machine_validator(events: str) -> str:
    """Validate a comma-separated event sequence and return a string classification."""
    if len(events) == 0:
        return "no_events"

    event_list = events.split(",")

    for event in event_list:
        if event not in KNOWN_EVENTS:
            return "unknown_event"

    if event_list[0] != "create":
        return "invalid_start"

    if len(event_list) == 1:
        return "incomplete_create"

    return _walk_transitions(event_list)
