"""psycopg read-modify-write helpers for the ideas board.

Every helper takes a psycopg cursor (or connection) so the caller owns
transaction and connection lifecycle — the pattern @crdb_retry requires,
since the decorator re-executes the whole operation on a serialization
conflict and each attempt needs a fresh transaction.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from idea import Idea

if TYPE_CHECKING:
    import psycopg


# tag::repo[]
def create_schema(cur: psycopg.Cursor) -> None:
    """Create the ideas table if it does not already exist."""
    cur.execute(
        "CREATE TABLE IF NOT EXISTS ideas ("
        "  id INT PRIMARY KEY DEFAULT unique_rowid(),"
        "  text STRING NOT NULL,"
        "  votes INT NOT NULL DEFAULT 0"
        ")"
    )


def seed(cur: psycopg.Cursor, text: str) -> int:
    """Insert one idea with zero votes and return its id."""
    cur.execute("INSERT INTO ideas (text) VALUES (%s) RETURNING id", (text,))
    return cur.fetchone()[0]


def find(cur: psycopg.Cursor, idea_id: int) -> Idea | None:
    """Return the full Idea row, or None if it does not exist."""
    cur.execute("SELECT id, text, votes FROM ideas WHERE id = %s", (idea_id,))
    row = cur.fetchone()
    return Idea(id=row[0], text=row[1], votes=row[2]) if row else None


def current_votes(cur: psycopg.Cursor, idea_id: int) -> int:
    """Read the current vote count — the READ half of read-modify-write."""
    cur.execute("SELECT votes FROM ideas WHERE id = %s", (idea_id,))
    return cur.fetchone()[0]


def update_votes(cur: psycopg.Cursor, idea_id: int, votes: int) -> None:
    """Write an absolute vote count — the WRITE half of read-modify-write."""
    cur.execute("UPDATE ideas SET votes = %s WHERE id = %s", (votes, idea_id))


def reset(cur: psycopg.Cursor, idea_id: int, votes: int = 0) -> None:
    """Reset an idea's vote count (used to re-run the two paths cleanly)."""
    cur.execute("UPDATE ideas SET votes = %s WHERE id = %s", (votes, idea_id))


# end::repo[]
