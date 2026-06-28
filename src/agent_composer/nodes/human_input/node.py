"""HUMAN_INPUT — a structural gate that suspends the run for a person.

Deliver-as-Output model: on its single run the node ALWAYS emits
`PauseRequested(HumanInputRequired)` and parks. The host satisfies the pause with a
`DeliverAnswerCommand(node_id=this_node, value=answer)`; the engine writes that value
as the node's `Output` (`pool.set` + fire the out-edges) — the node never re-runs. Its
single output value is the delivered answer.
"""

from typing import Any, Optional

from agent_composer.expr.template import render_template_record
from agent_composer.nodes.base import Node, NodeKind, Pause
from agent_composer.suspension.pause import HumanInputRequired


class HumanInputNode(Node):
    kind = NodeKind.HUMAN_INPUT

    def __init__(
        self,
        node_id: str,
        *,
        prompt: str,
        answer_schema: Optional[list[dict[str, Any]]] = None,
        title: Optional[str] = None,
    ) -> None:
        super().__init__(node_id, title=title)
        self.prompt = prompt
        self.answer_schema = answer_schema or []

    def run(self, inputs: dict):
        prompt = render_template_record(self.prompt, inputs)
        return Pause(
            HumanInputRequired(
                prompt=prompt,
                answer_schema=self.answer_schema,
                node_title=self.title,
                node_id=self.id,
            )
        )
