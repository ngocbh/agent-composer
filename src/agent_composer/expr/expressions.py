"""`${...}` reference resolution + the `when:` boolean expression evaluator.

Ported from the legacy engine's lark grammar, with one change: variable
resolution now goes through `TypedVariablePool.resolve`, so it reads typed
segments (and can traverse into object outputs — `${x.output.output.ratio}` —
which the old dict-of-str pool could not).

Grammar: comparisons (`==` `!=` `<` `<=` `>` `>=` `in` `not in`) over `${...}`
references and literals, combined with `and` / `or` / `not` and parentheses.
A bare reference with no comparison operator is rejected.
"""

import re
from typing import Any, Callable

from lark import Lark, Token, Transformer
from lark.exceptions import LarkError, VisitError

from agent_composer.state.pool import TypedVariablePool


class ExpressionError(ValueError):
    """A `when:` expression could not be parsed or evaluated."""


_VAR_RE = re.compile(r"\$\{([^}]+)\}")
_NUMBER_RE = re.compile(r"^-?\d+(\.\d+)?$")


def resolve_reference(path: str, pool: TypedVariablePool) -> Any:
    """Resolve a `${path}` reference against the pool (missing -> None)."""
    parts = [p for p in path.strip().split(".")]
    if not parts or any(not p for p in parts):
        raise ExpressionError(f"invalid variable path: '${{{path}}}'")
    head, *rest = parts
    return pool.resolve(head, rest)


def _resolve_in_record(path: str, record: dict) -> Any:
    """Resolve a `${path}` against a node's bound input record (dotted walk).

    A missing input / dotted miss / None step -> None: the LOCKED `when:` missing->falsy
    contract (the compile-time strict check rejects undeclared names, so a None here is a
    legitimate empty value, not an authoring error). Bare local-input refs only.
    """
    parts = [p.strip() for p in path.strip().split(".")]
    if not parts or any(not p for p in parts):
        raise ExpressionError(f"invalid variable path: '${{{path}}}'")
    value: Any = record.get(parts[0])
    for step in parts[1:]:
        value = value.get(step) if isinstance(value, dict) else None
    return value


def render_template(text: str, pool: TypedVariablePool) -> str:
    """Substitute every `${ref}` in `text` with its resolved value (str), against
    the whole pool (`node`/`system` namespaces).

    No production caller as of slice 5 — strict AGENT renders prompts against the
    bound input record via `render_template_record`. Retained (and test-pinned)
    for the open-namespace render path a future templated `HUMAN_INPUT` prompt
    will need. An UNRESOLVED reference (resolves to None) RAISES `ExpressionError`
    rather than silently rendering "" (the runtime floor for refs the compile-time
    check can't prove total).
    """

    def _sub(match: "re.Match[str]") -> str:
        ref = match.group(1)
        value = resolve_reference(ref, pool)
        if value is None:
            raise ExpressionError(f"unresolved reference ${{{ref}}} in template")
        return str(value)

    return _VAR_RE.sub(_sub, text)


def _parse_literal(token: str) -> Any:
    t = token.strip()
    if not t:
        raise ExpressionError("empty literal")
    low = t.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    if low in ("null", "none"):
        return None
    if _NUMBER_RE.match(t):
        return float(t) if "." in t else int(t)
    if (t.startswith('"') and t.endswith('"')) or (t.startswith("'") and t.endswith("'")):
        return t[1:-1]
    raise ExpressionError(f"cannot parse literal {token!r}")


def _arith(op: str, lhs: Any, rhs: Any) -> Any:
    """A binary arithmetic op over NUMBERS ONLY. A non-numeric operand —
    string/bool/null/None — is a loud `ExpressionError` (bool is excluded: it is
    `type bool`, not `int`)."""
    if type(lhs) not in (int, float) or type(rhs) not in (int, float):
        raise ExpressionError(f"arithmetic `{op}` requires numbers, got {lhs!r} {op} {rhs!r}")
    try:
        if op == "+":
            return lhs + rhs
        if op == "-":
            return lhs - rhs
        if op == "*":
            return lhs * rhs
        if op == "/":
            return lhs / rhs
        if op == "%":
            return lhs % rhs
    except ZeroDivisionError as exc:
        raise ExpressionError(f"division by zero: {lhs!r} {op} {rhs!r}") from exc
    raise ExpressionError(f"unsupported arithmetic operator: {op!r}")


def _eval_comparison(op: str, lhs: Any, rhs: Any) -> bool:
    try:
        if op == "==":
            return lhs == rhs
        if op == "!=":
            return lhs != rhs
        if op in ("in", "not in"):
            try:
                contained = lhs in rhs
            except TypeError as exc:
                raise ExpressionError(f"`in` rhs is not iterable: {exc}") from exc
            return contained if op == "in" else not contained
        # ordered comparisons: None on either side -> False (propagate falsy)
        if lhs is None or rhs is None:
            return False
        if op == "<":
            return lhs < rhs
        if op == "<=":
            return lhs <= rhs
        if op == ">":
            return lhs > rhs
        if op == ">=":
            return lhs >= rhs
    except TypeError as exc:
        raise ExpressionError(f"type error evaluating {lhs!r} {op} {rhs!r}: {exc}") from exc
    raise ExpressionError(f"unsupported operator: {op!r}")


_GRAMMAR = r"""
?start: or_expr

?or_expr: and_expr (OR and_expr)*
?and_expr: not_expr (AND not_expr)*
?not_expr: NOT not_expr   -> negate
         | comparison
?comparison: sum
           | sum COMP_OP sum   -> compare
           | sum IN sum        -> compare_in
           | sum NOT_IN sum    -> compare_notin

// arithmetic: numbers only at eval; a single value bubbles up unchanged.
?sum: product
    | sum "+" product   -> add
    | sum "-" product   -> sub
?product: factor
        | product "*" factor   -> mul
        | product "/" factor   -> div
        | product "%" factor   -> mod
?factor: atom
       | "-" factor   -> neg
?atom: REF | NUMBER | STRING | BOOL | NULL
     | list_lit
     | "(" or_expr ")"

// list literal: a value (the `in [...]` / `!= []` RHS) — elements are literals/refs
// (seeds 05/10 use `[]` and `["alpha", ...]`). Nested arithmetic isn't needed here.
list_lit: "[" [or_expr ("," or_expr)*] "]"

COMP_OP: "==" | "!=" | "<=" | ">=" | "<" | ">"
REF: /\$\{[^}]+\}/
STRING: /"[^"]*"/ | /'[^']*'/
NUMBER: /\d+(\.\d+)?/

NOT_IN.5: /not\s+in\b/
IN.4: /in\b/
AND.4: /and\b/
OR.4: /or\b/
NOT.4: /not\b/
BOOL.3: /true\b/ | /false\b/
NULL.3: /null\b/ | /none\b/

%import common.WS
%ignore WS
"""


class _Evaluator(Transformer):
    """Transforms a parsed `when:`/`asserts:` tree bottom-up: terminals resolve to
    VALUES (a `${ref}` via the resolve callable, literals to themselves), arithmetic
    nodes compute numbers, comparisons/boolean ops fold to bools."""

    def __init__(self, resolve: Callable[[str], Any]):
        super().__init__()
        self._resolve = resolve

    # --- terminals -> values (bottom of the transform) --- #
    def REF(self, tok):
        return self._resolve(str(tok)[2:-1])

    def NUMBER(self, tok):
        s = str(tok)
        return float(s) if "." in s else int(s)

    def STRING(self, tok):
        return str(tok)[1:-1]

    def BOOL(self, tok):
        return str(tok).lower() == "true"

    def NULL(self, tok):
        return None

    def list_lit(self, items):
        # elements are already values (refs/literals transformed bottom-up); an empty
        # `[]` yields []. This is the `in [...]` / `!= []` RHS value (seeds 05/10).
        return list(items)

    # --- arithmetic (operands already values; inline ops filtered) --- #
    def add(self, items):
        return _arith("+", items[0], items[1])

    def sub(self, items):
        return _arith("-", items[0], items[1])

    def mul(self, items):
        return _arith("*", items[0], items[1])

    def div(self, items):
        return _arith("/", items[0], items[1])

    def mod(self, items):
        return _arith("%", items[0], items[1])

    def neg(self, items):
        v = items[0]
        if type(v) not in (int, float):
            raise ExpressionError(f"unary minus requires a number, got {v!r}")
        return -v

    # --- comparisons (operands already values; COMP_OP/IN/NOT_IN kept) --- #
    def compare(self, items):
        lhs, op, rhs = items
        return _eval_comparison(str(op), lhs, rhs)

    def compare_in(self, items):
        return _eval_comparison("in", items[0], items[2])

    def compare_notin(self, items):
        return _eval_comparison("not in", items[0], items[2])

    # --- boolean combinators --- #
    def negate(self, items):
        operand = [i for i in items if not isinstance(i, Token)]
        return not operand[-1]

    def or_expr(self, items):
        return any(i for i in items if isinstance(i, bool))

    def and_expr(self, items):
        return all(i for i in items if isinstance(i, bool))


_PARSER = Lark(_GRAMMAR, parser="lalr", maybe_placeholders=False)


def _evaluate(expression: str, resolve: Callable[[str], Any]) -> bool:
    """Parse + evaluate a `when:` expression, resolving each `${ref}` via `resolve`."""
    try:
        tree = _PARSER.parse(expression)
    except LarkError as exc:
        raise ExpressionError(
            f"could not parse `when:` expression {expression!r}: must be one or more "
            f"comparisons combined with and/or/not. {exc}"
        ) from exc
    try:
        result = _Evaluator(resolve).transform(tree)
    except VisitError as exc:
        if isinstance(exc.orig_exc, ExpressionError):
            raise exc.orig_exc from None
        raise ExpressionError(str(exc.orig_exc)) from exc.orig_exc
    if isinstance(result, bool):
        return result
    raise ExpressionError(f"expression {expression!r} did not evaluate to a boolean")


def evaluate_when(expression: str, pool: TypedVariablePool) -> bool:
    """
    Evaluate a `when:` boolean expression against the variable pool.

    Parses and folds the expression — comparisons (`==` `!=` `<` `<=` `>` `>=` `in`
    `not in`) over `${...}` references and literals, combined with `and` / `or` / `not`
    — to a single boolean. This is the pool-based path, kept for manifest parse-checks and
    the deferred LOOP `while:` predicate seam; strict `CASE` uses the record-based path.

    Args:
        expression (`str`):
            The `when:` source: one or more comparisons combined with `and`/`or`/`not`.
            A bare reference with no comparison operator is rejected.
        pool (`TypedVariablePool`):
            The variable pool each `${ref}` resolves against (`node`/`system` namespaces).
            A reference that resolves to `None` participates as a falsy value.

    Returns:
        `bool`:
            The truth value of the expression.

    Raises:
        `ExpressionError`:
            If the expression is malformed, references an invalid path, mixes
            incompatible types, or does not evaluate to a boolean.

    Example:
        ```python
        evaluate_when("${score.output} >= 0.5 and ${flag.output}", pool)
        ```
    """
    return _evaluate(expression, lambda path: resolve_reference(path, pool))


def first_failing_assert(exprs, pool: TypedVariablePool):
    """The first assert expression in `exprs` that is false against `pool`, else None.

    The shared enforcement primitive for a flow's `asserts:` (boundary or post): `run_flow`
    uses it at the top-level boundary, and the REF/MAP child seam uses it to enforce a def's
    child-boundary asserts. Each expr is the `when:`/`asserts:` boolean grammar."""
    for expr in exprs:
        if not evaluate_when(expr, pool):
            return expr
    return None


def evaluate_when_record(expression: str, record: dict) -> bool:
    """Evaluate a strict-CASE `when:` against the node's bound input record.

    `${name}` / `${name.path}` resolve against `record`; a miss -> None, which is falsy
    through ==/!=/ordered comparisons (the locked `when:` missing->falsy contract).
    Note: `in`/`not in` with a None operand still raises (unchanged from the pool path).
    Bare local-input refs only; pool namespaces are not in scope (they belong in the
    node's input `from:` bindings).

    cf. `render_template_record` (strict AGENT), which RAISES on the same dotted miss.
    `when:` deliberately stays falsy so `default` can fire — so a dotted-key typo on a
    declared dict input routes to `default` silently until the `types:` registry can
    validate dotted paths at compile time (the head is checked today, not the path).
    """
    return _evaluate(expression, lambda path: _resolve_in_record(path, record))
