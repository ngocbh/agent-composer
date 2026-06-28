"""`run_flow(loaded, inputs) -> RunResult` — the run entrypoint.

A host-agnostic run boundary that drives a loaded `LoadedFlow` through the
`FlowEngine` and enforces its `asserts:` in two phases. It owns the run-input
concerns the pure graph engine doesn't:

- coerce + default the run arguments against the flow's `InputDecl`s,
- seed the `input` namespace + the host-ambient `system` clock,
- fire the BOUNDARY asserts (`${input}`/`${system}`-only) BEFORE any node runs
  (fail-fast), and the POST-TERMINAL asserts (`${<id>.output}`) AFTER the run
  reaches a terminal — flipping a succeeded run to `failed` on a false post assert.

`RunResult` (the surface-agnostic run outcome) lives here, beside `run_flow`. The
seeding fns (`coerce_inputs`/`apply_defaults`/`seed_system_clock`) come from
`state.seeding`; the run's clock is the `${system.today}`/`${system.now}` ambients
(a flow reads "as of" via `Optional[date]` + `:-`/`${system.today}`).

Never raises on a flow failure — a failed/aborted run, or a false assert, comes back as
a `RunResult` with `status != "succeeded"` (RunFailed is an engine EVENT, not an
exception). Compile-time errors (a bad flow) are surfaced by `load_flow`, not here.

Imports flow DOWN only: `runtime` (FlowEngine), `state` (the pool + seeding),
`expr` (evaluate_when), `events`, and the sibling `loader` (LoadedFlow). Nothing
imports back.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from agent_composer.events import RunAborted, RunFailed, RunPaused, RunSucceeded
from agent_composer.expr import first_failing_assert
from agent_composer.runtime.engine import FlowEngine
from agent_composer.state.pool import TypedVariablePool
from agent_composer.state.seeding import (
    apply_defaults,
    coerce_inputs,
    default_run_id,
    seed_system_clock,
)
from agent_composer.compose.loader import LoadedFlow

EventHook = Callable[[Any], None]

_STATUS: Dict[type, str] = {
    RunSucceeded: "succeeded",
    RunFailed: "failed",
    RunPaused: "paused",
    RunAborted: "aborted",
}


@dataclass
class RunResult:
    """The outcome of one flow run — surface-agnostic.

    `events` holds the raw engine event objects in order; a host serializes them
    as it sees fit. `input` is the run-arg dict (singular for surface symmetry).
    """

    input: Dict[str, Any]
    status: str
    output: Any = None  # the flow's single (possibly object) terminal value
    error: Optional[str] = None
    events: List[Any] = field(default_factory=list)
    checkpoint: Optional[Any] = None  # RunCheckpoint when paused (durable)
    engine: Optional[Any] = None  # live FlowEngine when paused (fast in-process)
    pause_reasons: List[Any] = field(default_factory=list)  # self-addressing PauseReasons


def run_flow(
    loaded: LoadedFlow,
    inputs: Dict[str, Any],
    *,
    run_id: Optional[str] = None,  # host-injected run id (${system.run_id}); minted if omitted
    on_event: Optional[EventHook] = None,
) -> RunResult:
    """Coerce `inputs`, seed the pool, enforce asserts, and drive the flow to a terminal.

    Returns a `RunResult` mirroring `run_flow`'s shape. A false BOUNDARY assert returns a
    `status="failed"` result BEFORE the engine runs (no node executes); a false
    POST-TERMINAL assert flips an otherwise-succeeded run to `status="failed"`.
    """
    coerced = apply_defaults(
        loaded.input, coerce_inputs(loaded.input, inputs)
    )

    pool = TypedVariablePool()
    seed_system_clock(pool)  # ${system.today}/${system.now} — once per run
    # ${system.run_id} — host-injected, else a freshly minted id; child-inherited like the clock.
    pool.add_system("run_id", run_id if run_id is not None else default_run_id())

    # The engine seeds store[START_ID] at run init (StartNode.run -> coerce/e08/defaults),
    # fires the boundary asserts pool-scoped (reading store[START_ID]), then advances START_ID. The
    # `inputs` namespace + run.py's add_inputs/e08/boundary-assert blocks are retired; the
    # e08 SegmentError + the false-boundary-assert both come back as a RunFailed engine event.
    engine = FlowEngine(
        loaded.compiled, pool,
        run_inputs=coerced, boundary_asserts=loaded.asserts.boundary,
    )
    events: List[Any] = []
    status = "incomplete"
    output: Any = None
    error: Optional[str] = None

    for event in engine.run():
        if on_event is not None:
            on_event(event)
        events.append(event)
        terminal = _STATUS.get(type(event))
        if terminal is not None:
            status = terminal
            if isinstance(event, RunSucceeded):
                output = event.output
            elif isinstance(event, RunFailed):
                error = event.error

    # A paused run carries the resume handles: the live engine (fast in-process),
    # a serializable checkpoint (durable), and the pause reasons.
    # `resume_flow` consumes these.
    if status == "paused":
        paused = [e for e in events if isinstance(e, RunPaused)]
        return RunResult(
            input=coerced,
            status="paused",
            events=events,
            engine=engine,
            checkpoint=engine.snapshot(),
            pause_reasons=paused[0].reasons if paused else [],
        )

    # Second assert phase — post-terminal asserts (${<id>.output[.X]}): only meaningful on a succeeded run;
    # a false one flips success to failure. Skipped if the run didn't succeed.
    if status == "succeeded":
        bad = first_failing_assert(loaded.asserts.post, pool)
        if bad is not None:
            status = "failed"
            error = f"assert failed: {bad}"

    return RunResult(
        input=coerced, status=status, output=output, error=error, events=events
    )


def resume_flow(
    loaded: LoadedFlow,
    *,
    engine: Optional[FlowEngine] = None,
    checkpoint: Any = None,
    commands: Optional[List[Any]] = None,
    on_event: Optional[EventHook] = None,
) -> RunResult:
    """Drive a suspended run to its next terminal via EITHER handle.

    Resume from a live `engine=` (fast in-process) OR a (deserialized) `checkpoint=`
    (durable, cross-process) — exactly one. External `commands` (the injected human
    answer / wait release) are applied before the run continues. Mirrors `run_flow`'s
    terminal-event loop and POST-TERMINAL asserts; a re-pause carries fresh handles.
    """
    if (engine is None) == (checkpoint is None):
        raise ValueError("resume_flow requires exactly one of engine= or checkpoint=")
    if engine is None:
        engine = FlowEngine.restore(loaded.compiled, checkpoint)

    events: List[Any] = []
    status, output, error = "incomplete", None, None
    for event in engine.resume(commands or []):
        if on_event is not None:
            on_event(event)
        events.append(event)
        terminal = _STATUS.get(type(event))
        if terminal is not None:
            status = terminal
            if isinstance(event, RunSucceeded):
                output = event.output
            elif isinstance(event, RunFailed):
                error = event.error

    if status == "paused":
        paused = [e for e in events if isinstance(e, RunPaused)]
        return RunResult(
            input={},
            status="paused",
            events=events,
            engine=engine,
            checkpoint=engine.snapshot(),
            pause_reasons=paused[0].reasons if paused else [],
        )

    if status == "succeeded":
        bad = first_failing_assert(loaded.asserts.post, engine.pool)
        if bad is not None:
            status, error = "failed", f"assert failed: {bad}"

    return RunResult(
        input={}, status=status, output=output, error=error, events=events
    )


def resume_command(loaded: LoadedFlow, reason: Any, value: Any):
    """Map a host-resumable `PauseReason` + an answer `value` to the engine command that
    delivers it. Dispatch on the reason SHAPE, never a static-graph lookup: the parked
    node may be a runtime-namespaced live id (e.g. `call_sub/w`, `agent/__ask#q1`) that exists
    only on `engine.flow.nodes` — `_apply_command` does the live lookup. A reason carrying a
    `node_id` delivers the answer as that leaf's Output (HUMAN_INPUT + WAIT release: value=None;
    the agent `ask_user` pause is now a namespaced HUMAN_INPUT leaf — no scratch
    coordinate). No `node_id` => not host-resumable (a bare `EventAwaited` a watcher satisfies)."""
    from agent_composer.suspension.commands import DeliverAnswerCommand

    node_id = getattr(reason, "node_id", None)
    if node_id is None:
        raise ValueError(f"pause reason {getattr(reason, 'type', '?')!r} is not host-resumable")
    return DeliverAnswerCommand(node_id=node_id, value=value)   # HUMAN_INPUT + WAIT (release: value=None)
