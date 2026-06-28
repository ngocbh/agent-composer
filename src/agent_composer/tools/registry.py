"""Tool registry + the ``@register_tool`` decorator.

A tool self-registers by decorating its implementation; importing the module
that defines it populates ``TOOL_REGISTRY`` as a side effect. The engine's TOOL
node and the AGENT tool-calling loop look tools up here by id.

This is the package's tool *seam*: the core ships no domain tools — a host
application registers its own (e.g. ``@register_tool("add")``). Tool ids must be
unique across everything registered into the process.
"""

from __future__ import annotations

from typing import Callable

from langchain_core.tools import BaseTool, StructuredTool

# Maps tool id -> the built LangChain tool. Populated by ``register_tool``.
TOOL_REGISTRY: dict[str, BaseTool] = {}


def register_tool(tool_id: str) -> Callable:
    """Register the decorated function as a tool under ``tool_id``.

    The function's docstring becomes the tool description the model sees. The
    original function is returned unchanged; the built LangChain tool is stored
    in ``TOOL_REGISTRY``. Raises on a duplicate id.
    """

    def decorator(fn: Callable) -> Callable:
        if tool_id in TOOL_REGISTRY:
            raise ValueError(f"Duplicate tool id '{tool_id}'")
        description = (fn.__doc__ or "").strip() or tool_id
        TOOL_REGISTRY[tool_id] = StructuredTool.from_function(
            fn, name=tool_id, description=description
        )
        return fn

    return decorator


def resolve_tools(tool_ids: list[str]) -> list[BaseTool]:
    """Look up tools by id, raising a clear error on unknown names."""
    resolved = []
    for tid in tool_ids:
        if tid not in TOOL_REGISTRY:
            raise ValueError(
                f"Unknown tool id '{tid}'. Known tools: {sorted(TOOL_REGISTRY)}"
            )
        resolved.append(TOOL_REGISTRY[tid])
    return resolved
