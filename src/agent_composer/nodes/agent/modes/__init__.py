"""Agent modes — the loop / prompting method (axis 1; one per node).

The mode contract lives in `common`, helper functions in `utils`; each concrete
mode lives in its own module and self-registers on import. Importing this package
populates `MODES` (before compile). Add a mode: drop a module here that
`@register_mode("name")`s a function (importing the contract from `.common`),
then import it below.

Tools/controls (axis 2) are the node's `tools` (data) + `controls` (control
tools). `plain` ignores them (single call); `tool_calling` binds and loops over
them. Control tools (e.g. `ask_user`, in `nodes/agent/controls/`) suspend the loop.
"""

from agent_composer.nodes.agent.modes.common import (
    DEFAULT_SYSTEM,
    AgentLoopError,
    AgentMode,
    AgentRunContext,
    MODES,
    register_mode,
)
from agent_composer.nodes.agent.modes.utils import text_of
from agent_composer.nodes.agent.modes import plain, tool_calling  # noqa: F401  register on import

__all__ = [
    "AgentRunContext",
    "AgentMode",
    "AgentLoopError",
    "MODES",
    "register_mode",
    "DEFAULT_SYSTEM",
    "text_of",
    "plain",
    "tool_calling",
]
