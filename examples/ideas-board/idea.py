"""Domain entity for the Concurrent Ideas Board example."""

from __future__ import annotations

# tag::entity[]
from dataclasses import dataclass


@dataclass
class Idea:
    """A single idea on the board.

    Attributes:
        id: Primary key assigned by CockroachDB.
        text: The idea's text.
        votes: Running upvote count — the hotly-contended column.
    """

    id: int
    text: str
    votes: int


# end::entity[]
