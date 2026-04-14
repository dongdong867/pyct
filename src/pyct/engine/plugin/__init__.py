"""Plugin subsystem for the concolic engine.

Plugins implement the Plugin Protocol and are registered with an Engine
instance via engine.register(plugin_instance). The engine fires events
at specific points in the exploration loop; plugins handle the events
they care about and ignore the rest.

Event semantics:
    Observer  — return value ignored, fire-and-forget
    Collector — all plugins run, list return values concatenated
    Resolver  — first non-None return wins, subsequent plugins skipped
"""

from pyct.engine.plugin.context import EngineContext
from pyct.engine.plugin.dispatcher import Dispatcher
from pyct.engine.plugin.protocol import Plugin

__all__ = ["Dispatcher", "EngineContext", "Plugin"]
