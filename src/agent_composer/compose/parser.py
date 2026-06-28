"""The section parser: Compose YAML text -> a strict `ComposeFile`.

This is the analogue of `manifest/parser.py`: `yaml.safe_load` -> wrap as a
strict Pydantic model -> raise `LoadError` on any violation. Three surface
rules shape it:

- **Top-level sections only** (`id`/`name`/`description?`/`inputs`/`nodes`/
  `outputs`/`asserts`/`typedefs`/`defs`/`uses`/`system`). `extra="forbid"` on the
  strict body makes a typo'd top-level key (e.g. `nodez:`) loud rather than silently
  dropped. (`uses:` = external callables; `system: paths:` = the resolution search
  path — NOT the strict `${system.X}` ambient namespace.)
- **`x-*` extension keys** at the top level are stripped before validation —
  custom metadata / YAML-anchor holders the engine ignores.
- **YAML anchors** (`&` / `*` / `<<:` merge) are expanded by PyYAML's
  `safe_load` *before* the strict schema sees the document.

`nodes` stays a raw `dict` here; per-kind node descriptors are a later step.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from agent_composer.compose.errors import LoadError
from agent_composer.compile.model import END_ID, START_ID

_STRICT = ConfigDict(extra="forbid")


def _normalize_section_keys(body: Any) -> Any:
    """Reject legacy `inputs:`/`outputs:` section keywords AT THE TOP LEVEL.

    Post-alias-delete: the dual-arm normalizer is a REJECTOR. A top-level flow with a
    legacy `inputs:` / `outputs:` section keyword raises a bespoke `LoadError` naming the
    retirement. The new singular `input:` / `output:` form is the only accepted spelling.

    NOTE: this function does NOT recurse into nested per-node or `defs:` bodies — the
    descriptor dataclasses (AgentDescriptor, CodeDescriptor, ...) keep their internal
    `inputs`/`outputs` field names (Python collection fields stay plural).
    The body-level back-map (`_phase3_back_map_to_plural`) translates the new singular
    keys to the dataclass field names. The rejector fires at the TOP-level only — if a
    flow author writes `inputs:` at any depth, the top-level rejector catches it via
    parse_file before _parse_node sees it.
    """
    if not isinstance(body, dict):
        return body
    for legacy, new in (("inputs", "input"), ("outputs", "output")):
        if legacy in body:
            raise LoadError(
                f"unknown top-level key {legacy!r} — flows use `{new}:` "
                f"(rename the section)"
            )
    return body


def _phase3_back_map_to_plural(body: Any) -> Any:
    """Map normalized `input`/`output` keys back to `inputs`/`outputs` for the dataclass
    constructors (transitional — the dataclass fields stay plural). Recurses into
    `nodes:`/`defs:`."""
    if not isinstance(body, dict):
        return body
    out = dict(body)
    if "input" in out:
        out["inputs"] = out.pop("input")
    if "output" in out:
        out["outputs"] = out.pop("output")
    if isinstance(out.get("nodes"), dict):
        out["nodes"] = {nid: _phase3_back_map_to_plural(nb) for nid, nb in out["nodes"].items()}
    if isinstance(out.get("defs"), dict):
        out["defs"] = {dname: _phase3_back_map_to_plural(db) for dname, db in out["defs"].items()}
    return out


class ComposeFile(BaseModel):
    """A parsed Compose flow — top-level sections, pre-node-descriptor.

    `inputs` / `nodes` / `typedefs` / `defs` stay raw dicts and `outputs` raw `Any` (a
    `${...}` binding string or a name -> binding map); later steps read each
    section into its typed form. `defs` holds in-file callables (each entry a sub-flow
    `{inputs?, nodes, outputs?, asserts?}`), resolved by a `call:` defs-first.

    A `model_validator(mode='before')` normalizes BOTH `inputs:` ↔ `input:` and
    `outputs:` ↔ `output:` (top-level + nested per-node + defs bodies) — see
    `_normalize_section_keys`. The dataclass fields keep the plural names; the
    normalizer rejects the legacy plural section keywords with a bespoke `LoadError`.
    """

    model_config = _STRICT

    id: str
    name: str
    description: Optional[str] = None
    version: Optional[str] = None  # opaque version tag (v1, 1.2.0, ...); None = unversioned
    inputs: dict[str, Any] = Field(default_factory=dict)
    nodes: dict[str, Any]
    outputs: Any = None
    asserts: list[str] = Field(default_factory=list)
    typedefs: dict[str, Any] = Field(default_factory=dict)
    defs: dict[str, Any] = Field(default_factory=dict)
    uses: dict[str, str] = Field(default_factory=dict)
    system: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _phase3_normalize_sections(cls, data: Any) -> Any:
        """Normalize `inputs:`/`outputs:` ↔ `input:`/`output:` BEFORE Pydantic validates.
        Recurses into nested `nodes:` + `defs:` bodies. Raises on ambiguous (both).

        The dataclass fields are still named `inputs`/`outputs` plural, so after
        normalization we map BACK to the plural names (`_phase3_back_map_to_plural`).
        The validator rejects the legacy plural section keywords with a bespoke message."""
        if not isinstance(data, dict):
            return data
        normalized = _normalize_section_keys(data)
        return _phase3_back_map_to_plural(normalized)


def _top_level_lines(text: str) -> dict[str, int]:
    """Best-effort map of top-level key -> 1-based source line (for loud errors).

    Returns {} if PyYAML can't compose the document (the strict validate below
    surfaces the real error); full source mapping is a later slice.
    """
    try:
        root = yaml.compose(text)
    except yaml.YAMLError:
        return {}
    if not isinstance(root, yaml.MappingNode):
        return {}
    lines: dict[str, int] = {}
    for key_node, _ in root.value:
        if isinstance(key_node, yaml.ScalarNode):
            lines[key_node.value] = key_node.start_mark.line + 1
    return lines


def section_lines(text: str) -> dict[str, int]:
    """Map each top-level section key -> its 1-based source line (best-effort).

    The public face of `_top_level_lines`, so the loader can locate a section-level
    error (e.g. a dangling flow-output ref at the `outputs:` line). Returns {} when
    PyYAML can't compose the document.
    """
    return _top_level_lines(text)


def parse_file(text: str) -> ComposeFile:
    """Parse Compose YAML text into a strict `ComposeFile`.

    Raises `LoadError` on malformed YAML, a non-mapping document, an unknown
    top-level key (after stripping `x-*`), or any schema violation.
    """
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise LoadError(f"invalid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise LoadError("a flow must be a YAML mapping at the top level")

    lines = _top_level_lines(text)
    body = {k: v for k, v in raw.items() if not str(k).startswith("x-")}

    # ComposeFile's model_validator(mode='before') normalizes section
    # keywords (input:↔inputs:, output:↔outputs:) at top + nested + defs bodies.
    # We pre-check unknown top-level keys here, allowing BOTH the new singular and the
    # legacy plural spellings.
    allowed_top = set(ComposeFile.model_fields) | {"input", "output"}
    for key in body:
        if key not in allowed_top:
            raise LoadError(
                f"unknown top-level key {key!r} "
                f"(allowed: {', '.join(sorted(set(ComposeFile.model_fields)))})",
                line=lines.get(key),
            )

    try:
        return ComposeFile.model_validate(body)
    except LoadError:
        raise
    except Exception as exc:  # pydantic ValidationError -> LoadError
        raise LoadError(str(exc)) from exc


# ---------- per-kind node descriptors ----------
#
# A `nodes:` entry is a keyed map (key = node id, no `id:` field) carrying a
# `kind:` plus FLAT kind-fields — the surface flattens `inputs:`/`outputs:`
# onto the node (vs the legacy spec's body wrappers, `spec/nodes.py`). These are
# DESCRIPTORS: the validated parsed shape per kind. Building the runtime `Node`
# (`output_shape` + `params` + flow `wiring`, `read_shape` over `outputs:`) happens
# later in the loader; here `inputs`/`outputs`/`args`/`cases` stay raw (binding strings / type nodes).
#
# Per-kind allowed fields mirror `spec/nodes.py:_validate_body_shape` in flat form
# (a field illegal for the kind is loud); `node_name`/`depends_on`/`runs_after` are common
# to every kind. `depends_on` and `runs_after` are RUN-ORDERING edges (no data flows): both
# gate on the source settling; `depends_on` co-skips the dependent if the source skipped,
# `runs_after` does not (the dependent still runs). See the loader edge pass.


@dataclass(frozen=True)
class AgentDescriptor:
    """kind=agent — an LLM reasoner (prompt + mode + optional tools/controls/llm)."""

    id: str
    inputs: dict[str, Any] = field(default_factory=dict)
    outputs: Any = None
    prompt: Optional[str] = None
    tools: list[str] = field(default_factory=list)
    controls: list[str] = field(default_factory=list)
    mode: str = "tool_calling"
    llm_config: dict[str, Any] = field(default_factory=dict)
    asserts: list[str] = field(default_factory=list)
    node_name: Optional[str] = None
    depends_on: list[str] = field(default_factory=list)
    runs_after: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CodeDescriptor:
    """kind=code — deterministic code (a `module:function` ref or a source snippet)."""

    id: str
    code: str
    inputs: dict[str, Any] = field(default_factory=dict)
    outputs: Any = None
    asserts: list[str] = field(default_factory=list)
    node_name: Optional[str] = None
    depends_on: list[str] = field(default_factory=list)
    runs_after: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ModelDescriptor:
    """kind=model — ML inference (a `model_id`, optional weights/runtime)."""

    id: str
    model_id: str
    inputs: dict[str, Any] = field(default_factory=dict)
    outputs: Any = None
    weights_uri: Optional[str] = None
    runtime: Optional[str] = None
    asserts: list[str] = field(default_factory=list)
    node_name: Optional[str] = None
    depends_on: list[str] = field(default_factory=list)
    runs_after: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ToolDescriptor:
    """kind=tool — a direct, deterministic call into TOOL_REGISTRY (untyped args)."""

    id: str
    tool_id: str
    args: dict[str, Any] = field(default_factory=dict)
    asserts: list[str] = field(default_factory=list)
    node_name: Optional[str] = None
    depends_on: list[str] = field(default_factory=list)
    runs_after: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CaseDescriptor:
    """kind=case — branch routing (searched `when:` or `on:`-value form).

    A `case` routes only — it carries NO `inputs:` (the desugar maps it
    onto the inputs-bearing `IfElseNode`). `else_` is the `else:` fallback.
    """

    id: str
    cases: list[dict[str, Any]] = field(default_factory=list)
    else_: Optional[str] = None
    on: Optional[str] = None
    asserts: list[str] = field(default_factory=list)
    node_name: Optional[str] = None
    depends_on: list[str] = field(default_factory=list)
    runs_after: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CallDescriptor:
    """kind=call|map — function application of a callable (`call:` + call-arg bindings).

    `call` names the callable, resolved **defs-first, else an external flow id** (the
    loader composes that resolution). `kind: call` is a single application (built as a plain
    `CallNode`); `kind: map` + `over: ${list}` is `List.map` — iteration with `${item}` in
    element scope (built as a `MapNode`), and `parallel:` overlaps the element runs. `inputs:`
    are the (per-element) call-arg bindings.

    `kind` is the REF/MAP discriminator: `"call"` (REF, the default) or `"map"`. The parser sets
    it from the YAML kind; the two SYNTH paths (inline-call + case desugar) keep the REF default
    (`over=None`). `build` branches on it: a `map` builds a `MapNode`, a `call` a `CallNode`.
    """

    id: str
    call: str
    inputs: dict[str, Any] = field(default_factory=dict)
    over: Optional[str] = None
    parallel: bool = False
    kind: str = "call"
    asserts: list[str] = field(default_factory=list)
    node_name: Optional[str] = None
    depends_on: list[str] = field(default_factory=list)
    runs_after: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class HumanInputDescriptor:
    """kind=human_input — suspend for a person; the typed answer is the node's output."""

    id: str
    prompt: str
    inputs: dict[str, Any] = field(default_factory=dict)
    outputs: Any = None
    asserts: list[str] = field(default_factory=list)
    node_name: Optional[str] = None
    depends_on: list[str] = field(default_factory=list)
    runs_after: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class WaitDescriptor:
    """kind=wait — suspend until a timestamp (until:); produces no value."""

    id: str
    until: str
    node_name: Optional[str] = None
    depends_on: list[str] = field(default_factory=list)
    runs_after: list[str] = field(default_factory=list)


NodeDescriptor = (
    AgentDescriptor
    | CodeDescriptor
    | ModelDescriptor
    | ToolDescriptor
    | CaseDescriptor
    | CallDescriptor
    | HumanInputDescriptor
    | WaitDescriptor
)

# Common keys every kind accepts (besides `kind` itself).
_COMMON_FIELDS = frozenset({"node_name", "depends_on", "runs_after"})

# Per-kind: (descriptor class, required flat fields, all allowed flat fields).
# `else` (a Python keyword) maps onto CaseDescriptor.else_.
_KIND_SPECS: dict[str, tuple[type, frozenset, frozenset]] = {
    "agent": (
        AgentDescriptor,
        frozenset(),
        frozenset({"inputs", "outputs", "prompt", "tools", "controls", "mode", "llm_config", "asserts"}),
    ),
    "code": (CodeDescriptor, frozenset({"code"}), frozenset({"code", "inputs", "outputs", "asserts"})),
    "model": (
        ModelDescriptor,
        frozenset({"model_id"}),
        frozenset({"model_id", "inputs", "outputs", "weights_uri", "runtime", "asserts"}),
    ),
    "tool": (ToolDescriptor, frozenset({"tool_id"}), frozenset({"tool_id", "args", "asserts"})),
    "case": (CaseDescriptor, frozenset({"cases"}), frozenset({"cases", "else", "on"})),
    # REF: a single application — `over:`/`parallel:` on `kind: call` is a LoadError (use `map`).
    "call": (
        CallDescriptor,
        frozenset({"call"}),
        frozenset({"call", "inputs", "asserts"}),
    ),
    # MAP: `List.map` — `over:` is required (the iteration source); `parallel:` overlaps elements.
    "map": (
        CallDescriptor,
        frozenset({"call", "over"}),
        frozenset({"call", "inputs", "over", "parallel", "asserts"}),
    ),
    "human_input": (
        HumanInputDescriptor,
        frozenset({"prompt"}),
        frozenset({"prompt", "inputs", "outputs", "asserts"}),
    ),
    "wait": (WaitDescriptor, frozenset({"until"}), frozenset({"until"})),
}


# YAML 1.1 (PyYAML `safe_load`) coerces the bare key `on:` to the boolean `True`
# (likewise `off`/`yes`/`no`). The case-node surface key `on:` is the only such
# key in a node body, so we map the coerced key back to its string form.
_YAML_BOOL_KEYS = {True: "on", False: "off"}


def _normalize_keys(body: dict) -> dict:
    """Undo YAML 1.1 boolean-key coercion for the surface key `on:`."""
    if not any(k in _YAML_BOOL_KEYS for k in body):
        return body
    return {_YAML_BOOL_KEYS.get(k, k): v for k, v in body.items()}


def _parse_node(node_id: str, body: Any, line: Optional[int]) -> NodeDescriptor:
    """Read one keyed-map node body into its typed per-kind descriptor."""
    if not isinstance(body, dict):
        raise LoadError(
            f"node {node_id!r}: body must be a mapping, got {type(body).__name__}",
            line=line,
        )
    if "#" in node_id or "/" in node_id:
        raise LoadError(
            f"node id {node_id!r} uses a reserved separator ('#'/'/' are reserved for "
            f"runtime graph expansion)",
            line=line,
        )
    if node_id in (START_ID, END_ID):
        raise LoadError(
            f"node id {node_id!r} is reserved for the synthesized START_ID/END_ID boundary"
            f"; authors write `input:`/`output:`, not a boundary node",
            line=line,
        )
    # Reserve the four singular head literals (input/output/system/item) so the
    # node-first ref `${<node>.output.k}` is unambiguous. Reserve the plural forms
    # (inputs/outputs) too as typo-catchers: combined with the _classify_path typo
    # hint post-migration, this makes migration typos loudly self-correcting.
    if node_id in ("input", "output", "system", "item"):
        raise LoadError(
            f"node id {node_id!r} is reserved (used as `${{{node_id}.X}}` as a "
            f"resolver head — pick a different node id)",
            line=line,
        )
    if node_id in ("inputs", "outputs"):
        raise LoadError(
            f"node id {node_id!r} is reserved (the plural head is retired — "
            f"rename to `{node_id[:-1]}` or pick a different node id)",
            line=line,
        )
    body = _normalize_keys(body)
    # Normalize the singular section keywords (`input:`/`output:` → back-mapped
    # to `inputs:`/`outputs:` plural that the descriptor dataclasses still use).
    # Direct callers of `_parse_node` (`parse_nodes`) get the same treatment as
    # `parse_file` does at the top level. The top-level rejector is in parse_file;
    # per-node we only run the back-map (legacy is already gone by the time we get here).
    body = _phase3_back_map_to_plural(body)
    kind = body.get("kind")
    if kind is None:
        raise LoadError(f"node {node_id!r}: missing `kind`", line=line)
    spec = _KIND_SPECS.get(kind)
    if spec is None:
        raise LoadError(
            f"node {node_id!r}: unknown kind {kind!r} "
            f"(allowed: {', '.join(sorted(_KIND_SPECS))})",
            line=line,
        )
    cls, required, allowed = spec
    allowed_keys = allowed | _COMMON_FIELDS | {"kind"}

    for key in body:
        if key not in allowed_keys:
            raise LoadError(
                f"node {node_id!r} (kind={kind}): field {key!r} is not allowed "
                f"(allowed: {', '.join(sorted(allowed_keys))})",
                line=line,
            )
    for key in required:
        if key not in body:
            raise LoadError(
                f"node {node_id!r} (kind={kind}): missing required field {key!r}",
                line=line,
            )
    # `asserts:` is a list of boolean-expression strings (the generic field-copy below does
    # no type-check, unlike the Pydantic-validated top-level `asserts`).
    asserts = body.get("asserts")
    if asserts is not None and not (
        isinstance(asserts, list) and all(isinstance(a, str) for a in asserts)
    ):
        raise LoadError(
            f"node {node_id!r} (kind={kind}): `asserts:` must be a list of strings",
            line=line,
        )

    kwargs: dict[str, Any] = {"id": node_id}
    # The REF/MAP discriminator: `kind: call|map` both build a CallDescriptor; `build` branches
    # on `.kind`. Every other kind has a 1:1 descriptor class, so `kind` is informational there.
    if cls is CallDescriptor:
        kwargs["kind"] = kind
    for key in allowed:
        if key not in body:
            continue
        # `else` -> the descriptor's `else_` field (reserved word).
        kwargs["else_" if key == "else" else key] = body[key]
    if "node_name" in body:
        kwargs["node_name"] = body["node_name"]
    if "depends_on" in body:
        kwargs["depends_on"] = body["depends_on"]
    if "runs_after" in body:
        kwargs["runs_after"] = body["runs_after"]
    return cls(**kwargs)


def parse_nodes(
    raw_nodes: dict[str, Any],
    node_lines: Optional[dict[str, int]] = None,
) -> dict[str, NodeDescriptor]:
    """Parse a `nodes:` mapping into typed per-kind descriptors keyed by node id.

    `node_lines` (node id -> 1-based source line) lets errors locate at the
    offending node's `.yaml` line; pass `_node_lines(text)` (or the ComposeFile's
    source map) for located errors.
    """
    lines = node_lines or {}
    out: dict[str, NodeDescriptor] = {}
    for node_id, body in (raw_nodes or {}).items():
        out[node_id] = _parse_node(node_id, body, lines.get(node_id))
    return out


def node_lines(text: str) -> dict[str, int]:
    """Map each `nodes:` entry's id -> 1-based source line (best-effort).

    Mirrors `_top_level_lines`: composes the document, descends into the `nodes:`
    mapping, and records each node-key's line. Returns {} if PyYAML can't compose.
    """
    try:
        root = yaml.compose(text)
    except yaml.YAMLError:
        return {}
    if not isinstance(root, yaml.MappingNode):
        return {}
    for key_node, value_node in root.value:
        if (
            isinstance(key_node, yaml.ScalarNode)
            and key_node.value == "nodes"
            and isinstance(value_node, yaml.MappingNode)
        ):
            return {
                k.value: k.start_mark.line + 1
                for k, _ in value_node.value
                if isinstance(k, yaml.ScalarNode)
            }
    return {}
