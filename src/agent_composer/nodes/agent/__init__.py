"""AGENT node package — one node, behavior = mode (the loop) + skills (tools).

`node` defines the single `AgentNode` and its `entry: Fresh | Resume` sum (a fresh agent
vs the resumed continuation of an `ask_user` pause); `modes/` holds the loop/prompting
methods (one per `mode`, registered in `MODES`). Agent modes talk to an LLM SDK directly
(see `node`).
"""

from agent_composer.nodes.agent.node import (
    AgentEntry,
    AgentNode,
    DEFAULT_MODE,
    Fresh,
    Resume,
)
from agent_composer.nodes.agent.modes import (
    MODES,
    AgentLoopError,
    AgentRunContext,
    register_mode,
)

__all__ = [
    "AgentNode",
    "AgentEntry",
    "Fresh",
    "Resume",
    "DEFAULT_MODE",
    "MODES",
    "AgentLoopError",
    "AgentRunContext",
    "register_mode",
]
