"""Engine event vocabulary — shared by nodes, the runtime, and callers.

Two tiers (graphon's "two-tier event model"):

- **Node events** are produced by `Node.run()`. A node emits `NodeStarted`, then
  optionally `StreamChunk`s (token streaming) and/or a `PauseRequested`, and
  terminates with `NodeSucceeded` or `NodeFailed`. The node only *describes* its
  one output value on `NodeSucceeded.output`; the engine — not the node — writes
  it into the variable pool. That split keeps nodes pure and testable.

- **Run events** are produced by `FlowEngine.run()` and streamed to the caller
  (the CLI): `RunStarted` then one terminal of
  `RunSucceeded | RunFailed | RunPaused | RunAborted`.

Plain dataclasses, not pydantic: these are transient in-process signals, never
serialized (what *is* serialized is the checkpoint, which captures pause
*reasons*, not events).

`PauseReason` is typed in `suspension.pause`; referenced here as `Any` to keep
`events` a dependency-free leaf alongside `state`.
"""

from dataclasses import dataclass, field
from typing import Any, Optional

# --------------------------------------------------------------------------- #
# Node-level events
# --------------------------------------------------------------------------- #


@dataclass
class NodeStarted:
    node_id: str


@dataclass
class StreamChunk:
    """A streamed fragment of a node's output (e.g. an LLM token)."""

    node_id: str
    key: str
    chunk: str
    final: bool = False


@dataclass
class NodeSucceeded:
    node_id: str
    output: Any = None  # the node's single produced value
    # IF_ELSE routing: which case handle was selected ("default" = fallback).
    edge_source_handle: Optional[str] = None


@dataclass
class NodeFailed:
    node_id: str
    error: str
    error_type: str = ""


@dataclass
class NodeExpanded:
    """A spawner (REF/MAP/AGENT) returned Enqueue(s); the dispatcher's
    _apply_enqueue grows the live graph. The node ran (value deferred to its alias filler)."""

    node_id: str
    enqueues: list = field(default_factory=list)


@dataclass
class PauseRequested:
    """A node cannot proceed until an external signal arrives.

    `reason` is a `suspension.pause.PauseReason` (HumanInputRequired /
    EventAwaited / ...). The engine resets the node and suspends the run.
    """

    node_id: str
    reason: Any


# Anything a node's `_run` generator may yield before returning its result.
NodeStreamEvent = (StreamChunk, PauseRequested)


# --------------------------------------------------------------------------- #
# Run-level events
# --------------------------------------------------------------------------- #


@dataclass
class RunStarted:
    pass


@dataclass
class RunResumed:
    """A resumed run's lead event (the `engine.resume()` twin of `RunStarted`)."""

    pass


@dataclass
class RunSucceeded:
    output: Any = None  # the flow's single (possibly object) terminal value


@dataclass
class RunFailed:
    error: str
    error_type: str = ""


@dataclass
class RunPaused:
    """The run suspended; `reasons` carry what each paused node is waiting for."""

    reasons: list[Any] = field(default_factory=list)


@dataclass
class RunAborted:
    pass
