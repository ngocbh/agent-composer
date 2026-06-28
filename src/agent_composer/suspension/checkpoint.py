"""RunCheckpoint — the serializable envelope that makes a run resumable.

The graph *topology* is intentionally NOT stored (it is rebuilt from the flow
spec), keeping checkpoints small and decoupled from code changes to node bodies.
Only run state is captured:

- `pool`            — the typed variable pool (lossless via AnySegment tags)
- `node_state` / `edge_state` — per-node/edge scheduling state
- `paused_nodes`    — parked leaves; stay TAKEN, the stored answer is delivered as Output on resume (no re-run)
- `deferred_nodes`  — became ready while suspending; enqueue on resume
- `pause_reasons`   — what each paused node awaits (drives the watcher/CLI)
- `expansions`      — descriptor tree for runtime-grown subgraphs (replayed on restore)

A round-trip through `dumps()`/`loads()` reconstructs an equivalent run in any
process.
"""

import json

from pydantic import BaseModel, Field

from agent_composer.compile.model import NodeState
from agent_composer.state.pool import TypedVariablePool
from agent_composer.suspension.expansions import Expansion
from agent_composer.suspension.pause import PauseReason

# Checkpoint blob schema version. 1.0 -> 2.0: the single-value store migration
# (pool.store collapsed node_id->key->Segment to node_id->Segment). 2.0 -> 3.0: the
# inputs-namespace retirement: `pool.inputs` is gone — `${input.X}`
# resolves via `store[START_ID]` — so the serialized pool shape changed.
# 3.0 -> 4.0: the type-surface rename (the `SegmentType.value` tags moved to the one
# Python-surface vocabulary, `str`/`int`/`float`/`bool`/..., so a pre-4.0 blob's
# `value_type` tags are unreadable by the AnySegment discriminated union). A pre-4.0
# blob is NOT loadable. 4.0 -> 5.0: adds the additive `expansions` field (the
# descriptor tree for runtime-grown subgraphs; defaults []). A 4.0 body is otherwise
# wire-compatible — `pause_reasons` is unchanged — but pre-5.0 blobs are rejected as a
# forward-compat hard cutover: this is the first build to write/expect the field, and a
# pre-5.0 checkpoint of a grown run carries no descriptors for the (forthcoming) replay.
# Pre-5.0 blobs are NOT loadable.
CHECKPOINT_VERSION = "5.0"


class RunCheckpoint(BaseModel):
    version: str = CHECKPOINT_VERSION

    pool: TypedVariablePool
    ready: list[str] = Field(default_factory=list)
    node_state: dict[str, NodeState] = Field(default_factory=dict)
    edge_state: dict[str, NodeState] = Field(default_factory=dict)
    paused_nodes: list[str] = Field(default_factory=list)
    deferred_nodes: list[str] = Field(default_factory=list)
    pause_reasons: list[PauseReason] = Field(default_factory=list)

    # Descriptor tree for runtime-grown subgraphs; `snapshot()` populates it
    # from `engine.expansions` and `restore()` replays it top-down (`_replay_expansions`) to
    # re-grow the cloned subgraphs before resume. Empty for any run that never expanded (pure
    # static flows).
    expansions: list[Expansion] = Field(default_factory=list)

    def dumps(self) -> str:
        return self.model_dump_json()

    @classmethod
    def loads(cls, blob: str) -> "RunCheckpoint":
        # Gate on the version from the RAW JSON BEFORE model validation: a 1.0 blob's
        # old nested-store shape would otherwise fail `extra="forbid"`/type validation
        # with an opaque pydantic error instead of this clear message.
        try:
            raw_version = json.loads(blob).get("version")
        except (ValueError, AttributeError):
            raw_version = None
        if raw_version != CHECKPOINT_VERSION:
            raise ValueError(
                f"incompatible checkpoint version {raw_version!r}; this build reads "
                f"{CHECKPOINT_VERSION!r} (adds the expansions descriptor tree)"
            )
        return cls.model_validate_json(blob)
