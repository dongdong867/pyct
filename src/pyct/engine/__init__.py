"""PyCT concolic exploration engine.

Public API:
    Engine: the exploration orchestrator
    Plugin: protocol for engine extensions
    EngineContext: read-only snapshot passed to plugin event handlers
    ExplorationResult: internal result produced by Engine.explore()
    RunConcolicResult: public result returned by pyct.run_concolic()
    ExplorationState: mutable state (engine-internal)
"""

from pyct.engine.engine import Engine
from pyct.engine.plugin.context import EngineContext
from pyct.engine.plugin.protocol import Plugin
from pyct.engine.result import ExplorationResult, RunConcolicResult
from pyct.engine.state import ExplorationState

__all__ = [
    "Engine",
    "EngineContext",
    "ExplorationResult",
    "ExplorationState",
    "Plugin",
    "RunConcolicResult",
]
