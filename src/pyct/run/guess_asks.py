"""What a guess ask is about and gives back, and the provider that answers it.

``GuessProvider`` is declared here, in the run layer that consumes it (``pyct.run.guesses``), and
implemented in ``pyct.llm.guesses``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from pyct.results.llm_asks import AskCost, Unanswered
from pyct.rewrite.provider import Side


@dataclass(frozen=True)
class AskedLine:
    """One cause a guess ask is about: its file by its module's dotted name, its lines, its cause
    in the request's words, each condition on the way to its first line with the side the line
    needs, in the order a run meets them, and the input that got furthest along that way, as
    JSON, with how it ended: ``returned``, or its failure's kind and detail. ``furthest`` and
    ``ended`` are None when no input got along the way."""

    module: str
    lines: tuple[int, ...]
    cause: str
    conditions: tuple[Side, ...] = ()
    furthest: str | None = None
    ended: str | None = None


@dataclass(frozen=True)
class GuessRequest:
    """What a guess ask is about.

    ``place`` is the target's spec and the ask's count among the run's guess asks, from 1, as
    ``<spec>#<n>``, which the recording names it by. ``code`` is the target's code and its
    same-package callees' (``code_context``), ``signature`` the target's as Python writes it,
    ``lines`` each cause asked about, in the moment's order, and ``classes`` the classes of the
    target module's folder (``class_listing``), empty when it defines none.
    """

    place: str
    code: str
    signature: str
    lines: tuple[AskedLine, ...]
    classes: str = ""


@dataclass(frozen=True)
class GuessReply:
    """The reply's guesses, each array item as its own JSON text, so each is checked alone.

    ``ignored`` says why the reply held nothing the tool could read, such as no JSON array.
    """

    items: tuple[str, ...]
    cost: AskCost
    ignored: str | None = None


class GuessProvider(Protocol):
    """Gives inputs that may reach missed lines. It never raises for an LLM problem: it returns
    Unanswered."""

    def guesses(self, request: GuessRequest) -> GuessReply | Unanswered: ...
