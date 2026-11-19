"""CDC: a changefeed webhook handler for the ideas table.

The ``@changefeed_handler`` decorator tags a function with table/operations/endpoint
metadata; ``ChangefeedHandlerRegistry`` parses an incoming webhook envelope into
``ChangefeedEvent``s and dispatches each to the handler. Insert/update events are
projected onto an ``Idea``; deletes (after-image is ``None``) are counted.

This mirrors the Java ``IdeaChangefeedHandler``: it is pure event-processing logic,
so it is fully exercised without a live changefeed (see ``test_cdc.py``). A real
webhook-sink changefeed is created with ``ChangefeedManager`` against a live
cluster; that path needs an enterprise license + a reachable sink, so — like the
Java demo — there is no CDC integration test here.
"""

from __future__ import annotations

from typing import Any

from idea import Idea

# tag::cdc-handler[]
from cockroachdb import changefeed_handler


class IdeaChangefeedHandler:
    """Turns ``idea`` changefeed events into ``Idea``s and tracks deletes."""

    TABLE = "ideas"

    def __init__(self) -> None:
        self.handled: list[Idea] = []
        self.deletes = 0

    @changefeed_handler(table=TABLE, operations=["insert", "update", "delete"])
    def on_change(self, event: Any) -> None:
        """Project an insert/update ``after`` image onto an ``Idea``; count deletes."""
        if event.after is None:  # delete: no after-image
            self.deletes += 1
            return
        after = event.after
        self.handled.append(
            Idea(id=after["id"], text=after["text"], votes=after["votes"])
        )


# end::cdc-handler[]
