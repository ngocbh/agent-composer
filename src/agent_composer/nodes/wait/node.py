"""WAIT — the internal suspend-until primitive (two modes).

Not exposed to flow authors directly: the WATCH composite is built from the event
mode, and a timed pause is built from the timed mode. The mode is selected by
which field is authored:

- `event_spec` set -> EVENT mode: suspend with `EventAwaited(node_id=self.id)` until
  the host watcher delivers the event payload as this node's `Output` (a
  `DeliverAnswerCommand`) and resumes the run.
- `until` set -> TIMED mode: resolve the `${...}` binding to an ISO timestamp and
  suspend with `ScheduledPause(resume_at=ts, node_id=self.id)`. Resume is
  command-driven — the host releases the wait by delivering `value=None` as this
  node's `Output`; the engine never reads wall-clock. `date`/`datetime` segments
  resolve to ISO strings, so the resolver accepts a str directly.

Both mirror HUMAN_INPUT's deliver-as-Output model: the node ALWAYS pauses on
its single run; the engine delivers the answer — no re-run.
"""

from typing import Any, Optional

from agent_composer.nodes.base import Node, NodeKind, Pause
from agent_composer.state.pool import TypedVariablePool
from agent_composer.suspension.pause import EventAwaited, ScheduledPause


def resolve_until(until_src: Any, pool: TypedVariablePool) -> str:
    """Resolve a WAIT `until` source to an ISO timestamp string.

    A `${...}` binding (or a literal) is evaluated against the pool; `date`/`datetime` segments
    resolve to ISO strings (returned as-is), a raw `.isoformat()` object is formatted defensively,
    anything else is a loud `ValueError`. Lifted out of `WaitNode` so the engine bind seam can
    pre-resolve `inputs["until"]` for a pure `WaitNode.run`."""
    from agent_composer.expr import eval_binding, parse_binding
    from agent_composer.expr.expressions import resolve_reference

    val = eval_binding(parse_binding(until_src), lambda path: resolve_reference(path, pool))
    if isinstance(val, str):
        return val  # date/datetime are stored/resolved as ISO strings
    if hasattr(val, "isoformat"):  # defensive: a raw date/datetime object
        return val.isoformat()
    raise ValueError(
        f"wait `until` ({until_src!r}) did not resolve to a date/datetime: {val!r}"
    )


class WaitNode(Node):
    kind = NodeKind.WAIT

    def __init__(
        self,
        node_id: str,
        *,
        is_timed: bool = False,
        event_spec: Optional[dict[str, Any]] = None,
        poll: Optional[dict[str, Any]] = None,
        title: Optional[str] = None,
    ) -> None:
        # The timed/event discriminator: a timed WAIT's `until` SOURCE lives on
        # `CompiledFlow.wiring[id]["until"]` (the node/flow split), not the node — `is_timed` is the
        # only residual; the engine pre-resolves the source into inputs["until"] before `run`.
        super().__init__(node_id, title=title)
        self.is_timed = is_timed
        self.event_spec = event_spec or {}
        self.poll = poll or {}

    def run(self, inputs: dict):
        # The engine pre-resolves a timed `until` into inputs["until"] (a concrete ISO ts);
        # its presence is the timed/event discriminator. `resolve_until` is the bind's job now.
        if "until" in inputs:  # timed mode
            return Pause(ScheduledPause(resume_at=inputs["until"], node_id=self.id))
        # event mode (unauthorable; WATCH) — the watcher delivers the payload as this node's Output
        return Pause(EventAwaited(event_spec=self.event_spec, poll=self.poll, node_id=self.id))
