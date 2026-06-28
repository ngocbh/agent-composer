"""CALL — the REF driver (`kind: call`), internal-only build target.

`CallNode` applies a callable ONCE (`'a flow -> 'b`). It is the REF half of the REF/MAP pair;
the MAP half is `nodes.map.MapNode` (`kind: map` + `over:`, `list['a] -> list['b]`) — the two are
distinct typed drivers. `CallNode` carries NO `over`/`parallel`.

`run` returns one `Enqueue` *description* — the engine's `_apply_enqueue` REF arm clones the baked
child + grows the live graph: `Enqueue(child, dict(inputs))` (the call-args RAW). The spliced child
START_ID owns omitted-input defaulting (its params carry default/required), so the driver no longer
pre-defaults. `child`/`child_inputs`/`child_asserts` are baked at load by
`compose.build` (`build_call_node`); `child_inputs` is read by compile validation
(`check_ref_map_types`) AND at runtime by the engine's boundary-assert temp pool (to mirror START_ID's
coerce+default view for the eager `${input.X}` check).
"""

from typing import Any, Optional

from agent_composer.nodes.base import Enqueue, Node, NodeKind


class CallNode(Node):
    kind = NodeKind.CALL

    def __init__(self, node_id: str, *, flow_id: str, flow_version: Optional[int] = None,
                 child: Any = None, child_inputs: Optional[list] = None, child_asserts: Any = None,
                 title: Optional[str] = None) -> None:
        super().__init__(node_id, title=title)
        self.flow_id = flow_id
        self.flow_version = flow_version
        self.child = child
        self.child_inputs = child_inputs or []
        self.child_asserts = child_asserts

    def run(self, inputs: dict, **caps: Any):
        if self.child is None:
            raise RuntimeError(f"CALL node {self.id!r}: child flow {self.flow_id!r} not baked")
        # Pass the call-args RAW: the spliced child START_ID owns omitted-input defaulting now (its
        # params carry default/required), so the driver no longer pre-defaults.
        return Enqueue(self.child, dict(inputs))
