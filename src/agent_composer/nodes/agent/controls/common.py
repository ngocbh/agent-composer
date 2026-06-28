"""Control-tool contract — the `ControlTool` shape + the registry.

Common (shared across the control-tool modules), kept out of `control/__init__.py`
so the concrete control tools import from here and `__init__` only re-exports +
imports them to register — no `__init__` <-> submodule cycle.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from langchain_core.tools import BaseTool

from agent_composer.suspension.pause import PauseReason


@dataclass
class ControlTool:
    """A tool whose call drives an engine effect instead of local execution.

    `tool` is the langchain schema bound to the model; `pause_reason` builds the
    `PauseRequested` payload from the call's args.
    """

    name: str
    tool: BaseTool
    pause_reason: Callable[[dict[str, Any]], PauseReason]


CONTROL_TOOLS: dict[str, ControlTool] = {}


def register_control_tool(control_tool: ControlTool) -> ControlTool:
    CONTROL_TOOLS[control_tool.name] = control_tool
    return control_tool
