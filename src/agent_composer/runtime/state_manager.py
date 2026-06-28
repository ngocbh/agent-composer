"""Mutable per-run scheduling state.

Owns the node/edge `NodeState` maps, the executing-nodes set, and the two
load-bearing predicates ported from graphon:

- `disposition` / `is_node_ready` — the edge-class-aware join: a control edge
  (`source_handle`) hard-gates (veto — all-skipped control => the node is `dead`,
  overriding TAKEN data edges); a required data group (`input_group`, `optional=False`)
  co-skips when all its edges are SKIPPED; an ordering edge (`ordering=True`, no data)
  gates on its source settling but only `depends_on` (`optional=False`) co-skips when the
  source skipped — `runs_after` (`optional=True`) is inert. A node with no control edge,
  all required data groups satisfied, and no co-skipping ordering edge skipped is `ready`; an
  unresolved (UNKNOWN) gate `wait`s. Edges from `__start__` are pseudo-edges (root seeded directly).
- `is_complete` — the whole graph is done when the ready queue is empty AND no
  node is executing.

A single `RLock` guards all of it. In the single-threaded drain it is
uncontended; under the worker pool it protects the dispatcher's mutations from
the workers' reads, preserving the single-writer invariant.
"""

import threading
from typing import TYPE_CHECKING

from agent_composer.compile.model import CompiledFlow, NodeState

if TYPE_CHECKING:
    from agent_composer.compile.model import Edge


class StateManager:
    def __init__(self, flow: CompiledFlow) -> None:
        self.flow = flow
        self.node_state: dict[str, NodeState] = {nid: NodeState.UNKNOWN for nid in flow.nodes}
        self.edge_state: dict[str, NodeState] = {e.id: NodeState.UNKNOWN for e in flow.edges}
        self.executing: set[str] = set()
        self.lock = threading.RLock()

    # --- edge / node marking ----------------------------------------------- #

    def mark_edge(self, edge_id: str, state: NodeState) -> None:
        with self.lock:
            self.edge_state[edge_id] = state

    def mark_node(self, node_id: str, state: NodeState) -> None:
        with self.lock:
            self.node_state[node_id] = state

    def register(self, node_ids: "list[str]", edges: "list[Edge]") -> None:
        """Runtime overlay: add UNKNOWN node/edge state for a freshly-added subgraph,
        atomically under the lock, before any of its nodes can become ready."""
        with self.lock:
            for nid in node_ids:
                self.node_state.setdefault(nid, NodeState.UNKNOWN)
            for edge in edges:
                self.edge_state.setdefault(edge.id, NodeState.UNKNOWN)

    # --- executing-set ------------------------------------------------------ #

    def add_executing(self, node_id: str) -> None:
        with self.lock:
            self.executing.add(node_id)

    def finish_executing(self, node_id: str) -> None:
        with self.lock:
            self.executing.discard(node_id)

    # --- predicates --------------------------------------------------------- #

    def real_incoming(self, node_id: str) -> "list[Edge]":
        # START_ID is now a real root NODE (it has no incoming edge of its own, so
        # real_incoming(START_ID) == [] -> disposition `ready`). A `START_ID->X` edge is an
        # ORDINARY incoming edge of X that gates X on START_ID settling, so it is no longer filtered.
        return list(self.flow.incoming(node_id))

    def disposition(self, node_id: str) -> str:
        """Classify a node given current edge state: 'ready' | 'wait' | 'dead'.

        The single source of truth for the run path (`is_node_ready`) and the skip path
        (`engine._skip_edge`), so the two never drift. Gates over the node's REAL incoming
        edges, partitioned by class (control = `source_handle` set; ordering = `ordering`;
        data = the rest, grouped by `input_group`):

        - VETO: a node with control edges is `dead` when ALL of them are SKIPPED (overriding
          any TAKEN data edge — the case-route hard gate); otherwise it needs >=1 control
          edge TAKEN to be `ready`.
        - DATA CO-SKIP: a co-skipping data group (`optional=False`) is `dead` when ALL its edges are
          SKIPPED; an optional group (a literal/`:?` escape) never forces `dead`.
        - ORDERING: a `depends_on` edge (`ordering=True, optional=False`) is `dead` when
          its source SKIPPED (per-edge AND); a `runs_after` edge (`optional=True`) is inert —
          both gate on the source settling via the UNKNOWN -> `wait` scan.

        DEAD is eager (a gate already impossible -> `dead` even while other edges are UNKNOWN,
        so the skip-flood propagates); else any UNKNOWN -> `wait`; all resolved & not dead ->
        `ready`. Edge state is monotonic (each edge marked once), so eager-dead can never skip
        a node that could still run.
        """
        with self.lock:
            real = self.real_incoming(node_id)
            if not real:
                return "ready"
            st = self.edge_state
            control = [e for e in real if e.source_handle is not None]
            ordering = [e for e in real if e.source_handle is None and e.ordering]
            data = [e for e in real if e.source_handle is None and not e.ordering]

            # eager DEAD: the veto (all control skipped) overrides data
            if control and all(st[e.id] == NodeState.SKIPPED for e in control):
                return "dead"
            # eager DEAD: a required data group fully skipped (co-skip)
            groups: dict[str, list] = {}
            for e in data:
                groups.setdefault(e.input_group, []).append(e)
            for edges_g in groups.values():
                if edges_g[0].optional:
                    continue  # group has a literal/`:?` escape -> never co-skips
                if all(st[e.id] == NodeState.SKIPPED for e in edges_g):
                    return "dead"
            # eager DEAD: a `depends_on` ordering edge (optional=False) whose source skipped
            # — AND semantics, per edge (a `runs_after` edge is optional=True, so inert here).
            for e in ordering:
                if not e.optional and st[e.id] == NodeState.SKIPPED:
                    return "dead"

            if any(st[e.id] == NodeState.UNKNOWN for e in real):
                return "wait"
            return "ready"

    def is_node_ready(self, node_id: str) -> bool:
        return self.disposition(node_id) == "ready"

    def is_complete(self, ready_is_empty: bool) -> bool:
        with self.lock:
            return ready_is_empty and not self.executing
