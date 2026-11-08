"""A method on a class whose constructor, and its annotations' text, come from another module."""

from tests.unit.run.ledger_base import Base


class Ledger(Base):
    def total(self) -> int:
        if self.owner == "admin":
            return 0
        return len(self.counts)
