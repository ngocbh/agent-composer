"""ask_user — a control tool: the agent asks the human a question mid-loop.

Bound to the model as `ask_user(question: str)`. When the model calls it, the
`tool_calling` loop suspends with `HumanInputRequired` instead of executing
locally; on resume the user's answer is fed back as the tool result. Schema only —
the function body is never invoked; the loop intercepts the call.

Model-chosen, NOT forced: granting `ask_user` only *enables* the capability — the
agent asks **only when the model decides it needs to** (so it's non-deterministic;
guide it via the prompt). For a guaranteed, deterministic pause (a mandatory human
gate that *always* suspends at a fixed point in the graph), use the `HUMAN_INPUT`
node (`agent_composer/nodes/human_input/`) instead.
"""

from __future__ import annotations

from langchain_core.tools import StructuredTool

from agent_composer.nodes.agent.controls.common import ControlTool, register_control_tool
from agent_composer.suspension.pause import HumanInputRequired


def _never_called(question: str) -> str:
    raise RuntimeError("ask_user is a control tool handled by the agent loop, not invoked directly")


register_control_tool(
    ControlTool(
        name="ask_user",
        tool=StructuredTool.from_function(
            _never_called,
            name="ask_user",
            description=(
                "Ask the human a question and wait for their answer. Use only when you "
                "need information that only the user can provide."
            ),
        ),
        pause_reason=lambda args: HumanInputRequired(prompt=str(args.get("question", ""))),
    )
)
