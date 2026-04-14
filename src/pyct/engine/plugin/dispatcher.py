"""Dispatcher — routes engine events to registered plugins."""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("ct.engine.dispatcher")


class Dispatcher:
    """Routes engine events to plugins based on event semantics.

    Plugins are ordered by their ``priority`` attribute (lower first),
    with registration order as the tiebreaker (via object id). Three
    dispatch modes mirror the three event semantics:

    - Observer: calls every plugin that implements the event, ignores
      return values. Exceptions in observer handlers are logged but
      do not propagate — observer plugins cannot break the engine.
      Used for lifecycle notifications.
    - Collector: calls every plugin that implements the event,
      concatenates list return values. Used for seed generation.
    - Resolver: calls plugins in priority order, stops at the first
      non-None return. Used for constraint resolution.

    Plugins without a handler for a given event are silently skipped
    via getattr, so partial implementations are fully supported.
    """

    def __init__(self, plugins: list):
        # Python's sorted() is stable, so equal priorities preserve
        # the original registration order as a natural tiebreaker.
        self._plugins = sorted(plugins, key=lambda p: p.priority)

    def dispatch_observer(self, event: str, ctx, *args) -> None:
        """Fire an observer event at every plugin that handles it.

        Exceptions raised by observer handlers are logged and
        suppressed — observer plugins cannot break the engine.
        """
        for plugin in self._plugins:
            handler = getattr(plugin, event, None)
            if handler is None:
                continue
            try:
                handler(ctx, *args)
            except Exception as e:
                log.warning(
                    "Plugin %s failed on %s: %s", plugin.name, event, e
                )

    def dispatch_collector(self, event: str, ctx) -> list:
        """Collect list results from every plugin that handles the event.

        Returns the concatenated list. Empty results are filtered out
        naturally — a plugin returning [] contributes nothing to the
        final list.
        """
        results: list = []
        for plugin in self._plugins:
            handler = getattr(plugin, event, None)
            if handler is None:
                continue
            result = handler(ctx)
            if result:
                results.extend(result)
        return results

    def dispatch_resolver(self, event: str, ctx, *args) -> Any:
        """Run resolver plugins in priority order, return first non-None.

        As soon as a plugin returns a non-None value, the dispatcher
        returns that value and subsequent plugins are NOT called.
        Returns None if every plugin returned None (or no plugins
        implement the event).
        """
        for plugin in self._plugins:
            handler = getattr(plugin, event, None)
            if handler is None:
                continue
            result = handler(ctx, *args)
            if result is not None:
                return result
        return None
