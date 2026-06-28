"""TOOL — a direct, deterministic invocation of one `TOOL_REGISTRY` entry.

No LLM in the loop (distinct from an AGENT's tool loop). The node's `args` are
compiled to (untyped) input bindings and resolved by the engine's `eval_node` bind
seam — a whole-string `${ref}` resolves against the pool, a literal passes through,
and every value is deep-copied (the tool sees only its own record `inputs`, never
the live pool). The registry tool is a LangChain `BaseTool`, invoked via
`.invoke(inputs)`.
"""

from agent_composer.nodes.base import Node, NodeKind, Output


class ToolNode(Node):
    kind = NodeKind.TOOL

    def __init__(self, node_id: str, *, tool_id: str, title=None) -> None:
        super().__init__(node_id, title=title)
        self.tool_id = tool_id

    def run(self, inputs: dict) -> Output:
        from agent_composer.tools import TOOL_REGISTRY

        if self.tool_id not in TOOL_REGISTRY:
            raise ValueError(
                f"node {self.id!r} references unknown tool {self.tool_id!r}; "
                f"known: {sorted(TOOL_REGISTRY)}"
            )
        result = TOOL_REGISTRY[self.tool_id].invoke(inputs)
        return Output(value=result)
