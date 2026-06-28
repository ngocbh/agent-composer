"""Control tools — engine capabilities the agent loop interprets specially.

A control tool is bound to the model like any tool (so the model can call it),
but the loop does NOT execute it via `TOOL_REGISTRY` — instead it performs an
engine effect. `ask_user` is the first: its call suspends the run
(`PauseRequested`) and resumes with the user's answer fed back as the tool result.

Lives in the engine (not `agent_composer.tools`, which is ordinary tools) because a control
tool participates in the suspend/resume protocol — it can't be a plain
`invoke(args) -> str`. A mode checks `CONTROL_TOOLS` before ordinary execution.
The contract is in `common`; the concrete tools self-register on import.
"""

from agent_composer.nodes.agent.controls.common import (
    CONTROL_TOOLS,
    ControlTool,
    register_control_tool,
)
from agent_composer.nodes.agent.controls import ask_user  # noqa: F401  register on import

__all__ = ["ControlTool", "CONTROL_TOOLS", "register_control_tool"]
