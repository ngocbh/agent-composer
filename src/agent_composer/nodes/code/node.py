"""CODE — run a deterministic Python callable referenced as `module:function`.

The function is called with its **bound typed input record** (a dict of the
node's declared inputs, resolved from their `from:` sources) — *not* the whole
pool — and returns the node's **one output value** (a scalar, list, or object;
"several outputs" = one object):

    def my_step(inputs: dict) -> Any: ...

The leaf function thus sees only its declared inputs (a pure function); the engine's
`eval_node` seam builds the record (the read boundary) and hands it in as `inputs`.

Inline source execution (the old engine's `exec` path) is intentionally *not*
supported here — it was the known sandbox-security gap. A `module:function`
reference keeps CODE deterministic and import-auditable; a real sandboxed inline
runtime is a separate, deliberate piece of work.
"""

import importlib

from agent_composer.nodes.base import Node, NodeKind, Output


class CodeNode(Node):
    kind = NodeKind.CODE

    def __init__(self, node_id: str, *, ref: str, title=None) -> None:
        super().__init__(node_id, title=title)
        if ":" not in ref:
            raise ValueError(
                f"CODE node {node_id!r} expects a 'module:function' reference, got {ref!r} "
                f"(inline source execution is not supported)"
            )
        self.ref = ref

    def run(self, inputs: dict) -> Output:
        module_name, _, func_name = self.ref.partition(":")
        module = importlib.import_module(module_name)
        func = getattr(module, func_name)
        result = func(inputs)  # strict: the user fn sees only its bound record
        return Output(value=result)  # the one value (object/list/scalar), stored whole
