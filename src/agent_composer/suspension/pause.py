"""PauseReason — a discriminated union describing *what a suspended node awaits*.

This is the typed payload on `PauseRequested` and the thing a checkpoint persists
so a scheduler/watcher knows when to wake the run. Adding a new way to wait is a
new subclass, nothing else.

Maps to the user-facing surface:
- HUMAN_INPUT node          -> HumanInputRequired (re-prompt on resume)
- WATCH composite's WAIT     -> EventAwaited (watcher fires -> resume)
- a plain timed wait         -> ScheduledPause
"""

from typing import Annotated, Any, Literal, Optional, Union

from pydantic import BaseModel, Field


class HumanInputRequired(BaseModel):
    type: Literal["human_input_required"] = "human_input_required"
    prompt: str
    # IOField-shaped expected answer (loose dicts; the CLI renders against it).
    answer_schema: list[dict[str, Any]] = Field(default_factory=list)
    node_title: Optional[str] = None
    # LOGICAL resumption identity: the node that paused. The agent `ask_user` pause is now a
    # namespaced HUMAN_INPUT leaf, so `compose.run.resume_command` delivers the answer
    # as that leaf's Output keyed on `node_id` — the `slot` field is vestigial (always None for
    # the leaf-pause model; the resume-plumbing prune is a later cleanup step).
    node_id: Optional[str] = None
    slot: Optional[str] = None


class EventAwaited(BaseModel):
    type: Literal["event_awaited"] = "event_awaited"
    # what to watch (a condition over a source) + how often to re-check.
    event_spec: dict[str, Any] = Field(default_factory=dict)
    poll: dict[str, Any] = Field(default_factory=dict)
    # LOGICAL resumption identity: the WAIT node whose watcher payload the host
    # delivers as the node's Output. None (default) => not host-resumable (a bare
    # EventAwaited() an external watcher satisfies; resume_command rejects it).
    node_id: Optional[str] = None


class ScheduledPause(BaseModel):
    type: Literal["scheduled_pause"] = "scheduled_pause"
    resume_at: Optional[str] = None  # ISO timestamp; None = "until poked"
    # LOGICAL resumption identity: the node whose timed wait the host releases.
    node_id: Optional[str] = None


PauseReason = Annotated[
    Union[HumanInputRequired, EventAwaited, ScheduledPause],
    Field(discriminator="type"),
]
