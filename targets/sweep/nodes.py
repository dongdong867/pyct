"""A sweep fixture: classes whose constructors take an object of their own class."""

from __future__ import annotations


class Node:
    def __init__(self, next: Node) -> None:
        self.next = next


class Link:
    def __init__(self, next: Link | None) -> None:
        self.next = next


def follow(head: Node) -> Node:
    return head.next


def walk(head: Link) -> int:
    if head.next is None:
        return 1
    return 2
