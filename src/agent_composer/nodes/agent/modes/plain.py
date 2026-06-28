"""plain mode — a single LLM call. No tools, no loop.

The simplest agent: render the prompt, ask the model once, return its text. Any
skills on the node are ignored (there is no loop to invoke them). Good for pure
generation/synthesis nodes.
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from agent_composer.nodes.agent.modes.common import DEFAULT_SYSTEM, AgentRunContext, register_mode
from agent_composer.nodes.agent.modes.utils import text_of
from agent_composer.nodes.agent.structured import shape_to_schema, _unwrap
from agent_composer.nodes.base import Output


@register_mode("plain")
def plain(ctx: AgentRunContext) -> Output:
    msgs = [SystemMessage(content=DEFAULT_SYSTEM), HumanMessage(content=ctx.prompt)]
    # A declared non-text shape -> structured generation; a bare str/Literal -> text path.
    schema = shape_to_schema(ctx.output_shape) if ctx.output_shape is not None else None
    if schema is None:
        return Output(value=text_of(ctx.model.invoke(msgs)))
    obj = ctx.model.with_structured_output(schema).invoke(msgs)
    return Output(value=_unwrap(obj, ctx.output_shape))

