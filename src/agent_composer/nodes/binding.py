"""Input binding — resolve a node's declared params into a typed input record (the read boundary).

The node/flow split: a node declares its signature as `ParamDecl`s (name + required/default/type,
NO source); the flow owns the sources in `CompiledFlow.wiring[node_id][param]`. `bind_params`
joins each `ParamDecl` to its `wiring[name]` source (an `expr.template` value — a whole `${...}`
resolved against the pool with type preserved, an embedded `${...}` stringified, or a literal),
building the `{name: value}` record the engine's `eval_node` hands the node instead of the pool.
Type-checking reuses the `shape_for` / `build_segment_with_type` helpers and stays lenient
on record / variant types that can't resolve against the empty registry.

A MAP body binds a per-element `item` scope: `${item}` / `${item.path}` resolve from the current
element passed via the `item=` kwarg (a body-local scope, NOT a pool head). The default (`item`
unset) is the ordinary non-MAP bind path.

Imports `expr` (parse_binding / eval_binding / resolve_reference) + `state` (shape_for /
build_segment_with_type); both sit below/beside `nodes` in the layer ladder.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Optional

from agent_composer.expr import (
    ExpressionError,
    RequiredError,
    eval_binding,
    parse_binding,
    resolve_reference,
)
from agent_composer.state import SegmentError, Shape, build_segment_with_type, shape_for
from agent_composer.state.pool import TypedVariablePool


class BindingError(ValueError):
    """A node's declared input could not be bound (missing-required or type mismatch)."""


@dataclass(frozen=True)
class ParamDecl:
    """One declared input on a node — the node-side half of the node/flow split (the flow-side half
    is `CompiledFlow.wiring[node_id][name] -> source`). A `ParamDecl` holds NO `source`: the node
    declares only its signature; the flow owns the wiring. `type=None` is an UNTYPED param (TOOL
    args); `shape` is the compile-stamped resolved type."""

    name: str
    type: Optional[str] = None
    required: bool = False
    default: Any = None
    shape: Optional[Shape] = None


def _resolve_source(source: Any, pool: TypedVariablePool, item: Any = None) -> Any:
    """Resolve a binding's `source` to a value via the `expr.template` language.

    A value that is exactly one `${...}` yields the **typed** value of that reference
    (type preserved); a `${...}` embedded in surrounding text is **stringified** into
    it; a value with no `${...}` is a plain literal (after `$$` -> `$`). The interior
    is a `|` coalesce, first-non-None, where an atom is a ref, a `:-` literal-or-
    one-nested-`${...}` default, a `:?` required, or a literal. `${item}` / `${item.path}`
    resolve from the MAP-body-local scope. A non-string `source` is a literal.

    Parse/eval errors (malformed ref, two-level nesting, an unbound `:?`) surface as
    `BindingError` — `expr`'s `ExpressionError`/`RequiredError` never leak across the
    `nodes <- expr` boundary."""
    if not isinstance(source, str):
        return source
    try:
        segments = parse_binding(source)
        return eval_binding(segments, lambda path: resolve_reference(path, pool), item)
    except (RequiredError, ExpressionError) as exc:
        raise BindingError(str(exc)) from exc


def bind_params(
    params: list[ParamDecl],
    wiring: dict[str, Any],
    pool: TypedVariablePool,
    *,
    item: Any = None,
) -> dict[str, Any]:
    """Resolve each declared `ParamDecl` into a typed record, joining the param to its source
    from the flow-owned `wiring` dict (`wiring[name] -> source`): coalesce / default / required /
    shape-check / deep-copy / `item` scope — the engine's read boundary.

    Raises `BindingError` on a missing-required input or a type mismatch.
    """
    record: dict[str, Any] = {}
    for p in params:
        present = p.name in wiring  # an absent edge (caller OMITTED) vs a present one (incl. bound-null)
        source = wiring.get(p.name)
        value = _resolve_source(source, pool, item)
        if value is None:
            # Distinguish an OMITTED input (no wiring edge) from one BOUND-TO-NULL (an edge that
            # resolves to None): only an omitted input fills its declared default / fails when
            # required — a caller's explicit null SHADOWS the child default (`f(x=None)` semantics,
            # the apply_defaults contract). In practice only START_ID's params carry default/required
            # (every other kind builds bare ParamDecls), so this refinement is inert elsewhere; it
            # is what lets the spliced child START_ID own omitted-input defaulting.
            if not present and p.default is not None:
                value = p.default
            elif not present and p.required:
                raise BindingError(f"required input {p.name!r} is unbound (from={source!r})")
            else:
                record[p.name] = None
                continue
        shape = p.shape
        if shape is None and p.type is not None:
            try:
                shape = shape_for(p.type, {})
            except SegmentError:
                shape = None
        if shape is not None:
            try:
                value = build_segment_with_type(shape, value).to_object()
            except SegmentError as exc:
                raise BindingError(f"input {p.name!r}: {exc}") from exc
        record[p.name] = copy.deepcopy(value)
    return record
