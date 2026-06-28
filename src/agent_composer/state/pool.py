"""TypedVariablePool — the runtime state primitive for a flow run.

A node produces exactly ONE value: `store[node_id]` is a single typed `Segment`
(scalar, object, or list) — "multiple outputs" are fields of one object. `${input.X}`
resolves to `store[<start_id>].X` — the synthesized START_ID node's committed bound-input
record IS the flow's run-arguments object (the standalone `inputs` namespace is
retired). The one side namespace is `system` (host-injected ambient — run id / clock /
tenant; reserved, run-global). There is no engine-private key-addressed namespace:
the agent tool-loop memo rides as graph data on the agent resume continuation, and
HUMAN_INPUT/WAIT answers are delivered as the parked leaf's Output.

Two responsibilities:
- `resolve(head, rest)` backs the `${...}` expression evaluator. Because values
  are typed objects (not stringified), `${x.output.ratio}` traverses into an
  object output; `${x.output}` is the node's whole value.
- `dumps()/loads()` serialize the whole pool losslessly (the discriminated
  `AnySegment` union round-trips each value's exact type), which is the state
  half of a durable checkpoint.
"""

from typing import Any, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from agent_composer.state.segments import (
    AnySegment,
    Segment,
    SegmentType,
    Shape,
    build_segment,
    build_segment_with_type,
)


class TypedVariablePool(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # node_id -> the node's single produced value (${<id>.output[.path]})
    store: dict[str, AnySegment] = Field(default_factory=dict)
    # ${system.<key>}  — host-injected ambient (run id / clock / tenant); reserved
    system: dict[str, AnySegment] = Field(default_factory=dict)
    # The enclosing flow's START_ID node id: `${input.X}` ≡ `store[start_id].X`. The
    # engine sets this per-flow (and seeds store[start_id] with the bound input record); the
    # default below is the top-level convention used by standalone/no-engine pools. The literal
    # MIRRORS `StartNode.ID` but is NOT imported from it: `state` is a leaf below `nodes`, so it
    # cannot import the node class. A consistency test pins `TypedVariablePool().start_id ==
    # StartNode.ID` so the two can never silently diverge.
    start_id: str = "__start__"

    # --- writes ------------------------------------------------------------- #

    def set(
        self,
        node_id: str,
        value: Any,
        declared: Optional[Union[SegmentType, Shape]] = None,
    ) -> None:
        """Store a node's single produced value. `declared` (a SegmentType or
        structural Shape) enables the write-time type/shape check."""
        self.store[node_id] = (
            build_segment_with_type(declared, value)
            if declared is not None
            else build_segment(value)
        )

    def add_system(self, key: str, value: Any) -> None:
        self.system[key] = build_segment(value)

    # --- reads -------------------------------------------------------------- #

    def get_segment(self, node_id: str) -> Optional[Segment]:
        return self.store.get(node_id)

    def get(self, node_id: str, default: Any = None) -> Any:
        seg = self.store.get(node_id)
        return seg.to_object() if seg is not None else default

    def resolve(self, head: str, rest: list[str]) -> Any:
        """Resolve a parsed `${head.rest...}` reference to a plain value.

        Namespaces:
          input.<key>[.<path>...]   -> store[start_id].<key>
          <node>.output[.<path>...] -> store[node_id].<path>  (`.output` is a
                                       syntactic discriminator the resolver SKIPS)
          system.<key>              -> system[key]  (host-ambient; reserved)

        Legacy plural surfaces (`${outputs.X}` / `${inputs.X}`) are rejected at LOAD
        time by `_classify_path` with a typo hint. At RUNTIME, an
        unrecognized head (whether a legacy plural typo or a stray name) resolves to
        None per the missing-ref-is-falsy contract (`when:` clauses route to default
        rather than fail-loud). This is intentional but means a runtime-injected
        legacy ref will silently propagate as None — the load-time guard is the
        authoritative defense.
        """
        # Node-first head — `${<node>.output[.path]}` reads `store[<node>]` interior.
        # The literal `output` token is a syntactic discriminator and is SKIPPED.
        if head in self.store and rest and rest[0] == "output":
            return self._traverse(self.store.get(head), rest[1:])
        # Singular input head — `${input.k}` ≡ `store[start_id].k`.
        if head == "input":
            if not rest:
                return None
            key, *path = rest
            return self._traverse(self.store.get(self.start_id), [key, *path])
        if head == "system":
            seg = self.system.get(rest[0]) if rest else None
            return seg.to_object() if seg is not None else None
        return None

    @staticmethod
    def _traverse(seg: Optional[AnySegment], path: list[str]) -> Any:
        """Object-walk a stored Segment along `path` (the `${<id>.output.a.b}` /
        `${input.x.y}` dotted read); a missing step resolves to None (propagates falsy)."""
        if seg is None:
            return None
        value = seg.to_object()
        for step in path:
            value = value.get(step) if isinstance(value, dict) else None
            if value is None:
                return None
        return value

    # --- serialization ------------------------------------------------------ #

    def dumps(self) -> str:
        return self.model_dump_json()

    @classmethod
    def loads(cls, blob: str) -> "TypedVariablePool":
        return cls.model_validate_json(blob)
