---
name: composing-agents
description: Use when authoring an Agent Composer flow — writing or editing a flow YAML, building an agent workflow, wiring nodes (agent / code / tool / case / human_input / wait / call / map), or answering "how do I write a flow that …". Trigger on "create an agent", "write a flow", "compose a workflow", "add a node to my flow", "how do I branch / loop / call another flow", or any `ac run` flow-authoring request.
---

# Composing an agent workflow

An Agent Composer **flow is a function**: a typed `input:`, a graph of `nodes:`,
and a typed `output:`. You never draw edges — the engine **infers the graph from
the `${...}` references** between nodes. The human owns the structure; the LLM
only fills the leaf boxes.

Full reference: [`docs/syntax.md`](../../../docs/syntax.md). Working flows:
[`examples/`](../../../examples). This skill is the authoring workflow + the parts
that bite.

**Companions:** [`reference.md`](reference.md) — operators, the three expression
contexts, type forms, recipes, and gotchas. [`templates/`](templates/) — minimal
loadable starter flows for each shape (single agent, agent→code pipeline,
branch+join, tool use, human gate, `call`/`map` composition); copy one and edit.

## The workflow — author a flow in order

1. **State the function.** Write the one-line job, then its **signature**: what
   typed values come in (`input:`) and what comes out (`output:`). If you can't
   name the input and output types, the design isn't done.
2. **Name reusable types** in `typedefs:` (enums, records, aliases).
3. **Decompose into leaf nodes.** Each node is one step: an LLM call (`agent`),
   deterministic code (`code`), a registered tool (`tool`), a branch (`case`), a
   human gate (`human_input`), a timed pause (`wait`), or a child-flow call
   (`call`/`map`). Prefer many small typed nodes over one mega-prompt.
4. **Wire by reference, not by edges.** A node consumes another by putting
   `${producer.output}` in its `input:` block. That reference *is* the edge.
5. **Bind the flow `output:`** to the terminal node(s).
6. **Add `asserts:`** for invariants that must hold (boundary or post checks).
7. **Validate, then run** (see "Validate & run").

## The flow skeleton

```yaml
id: my-flow                  # stable identifier (no spaces)
name: my_flow                # display name
description: One line.       # optional

typedefs:                    # optional — named/composed types
  Verdict: Literal[go, no_go, wait]

input:                       # the parameters — typed
  question: str
  audience: Optional[str]    # nullable; omitted -> null
  lookback: int = 30         # default-fill when omitted

nodes:                       # the body — a map keyed by node id (no per-node id:, no wrappers)
  step_a:
    kind: agent
    input: { question: ${input.question} }
    output: str
    prompt: "Answer: ${question}"

output: ${step_a.output}     # one value, OR a multi-field object (see below)

asserts:                     # optional — boolean invariants
  - ${step_a.output} != ""
```

There is **no `edges:` block**, no `__start__`/`__end__`, no per-node `id:`, and
no body wrappers — a node body is flat.

## References — how you wire values

| Write | Means |
|-------|-------|
| `${input.X}` | field `X` of the flow input |
| `${node.output}` | node `node`'s whole (typed) value |
| `${node.output.field}` | dot into an object value |
| `${name}` (bare) | **only inside a `prompt:` or a `case` `when:`** — that node's own declared input |

A whole-string `${ref}` resolves to the **typed value**; embedded in surrounding
text it is **stringified**.

**Operators inside `${...}`:**

| Form | Meaning |
|------|---------|
| `${X:-default}` | value, else `default` if absent |
| `${X:?msg}` | required — fail with `msg` if absent |
| `${a \| b \| c}` | first present among peers — **the branch-join coalesce** |
| `$$` | a literal `$` |

Nesting is allowed: `${a:-${b:-lit}}`.

## Types

Python typing vocabulary. Scalars: `str`, `int`, `float`, `bool`, `date`,
`datetime`, `object`, `None`. Forms: `list[X]`, `Optional[X]`, `Literal[...]` (an
enum of tags), and named **records**. `Optional[X]` (nullable) and `= default`
(omission-fill) are orthogonal.

```yaml
typedefs:
  Basket: list[str]                    # alias (aliases compose)
  Decision: Literal[go, no_go, wait]   # enum — one of these tags
  Signal:                              # record — fields recurse
    score: float
    note: Optional[str]
```

## Node kinds (the closed set — you compose these, you don't define new ones)

### `agent` — an LLM leaf
```yaml
classify:
  kind: agent
  mode: plain                  # "plain" = one call; "tool_calling" (default) = a tool loop
  input:
    text: ${input.text}        # bindings — these infer the data edges
  output: Literal[positive, neutral, negative]
  prompt: |-
    Classify the sentiment of: ${text}
    Answer with exactly one of: positive, neutral, negative.
```
**An AGENT's `output:` may be any shape.** A bare `str` or a `Literal[...]` enum
(the model answers with one tag) keeps the agent a text producer. A record,
`float`, `int`, `bool`, or list switches it to **structured generation** — the
engine derives a schema from `output:` and the model emits a conforming value
(native structured output, or a JSON fallback for providers that lack it), validated
at the write boundary and retried up to `retries:` times (default 2) on deviation.
Use a downstream `code`/`model` node only for deterministic post-processing. To give
an agent ordinary tools: `tools: [tool_id, ...]` (requires `mode: tool_calling`).
A node may pin its model via `llm_config:`; otherwise the environment defaults apply.

### `code` — deterministic Python
```yaml
verdict:
  kind: code
  input:
    s: ${score.output.signal}
  output: Signal               # unlike an agent, ANY type
  code: pkg.mod:fn             # module:function
```

### `tool` — a registered tool (no LLM)
```yaml
news:
  kind: tool
  tool_id: get_facts           # a TOOL_REGISTRY key
  args:                        # untyped — each value is a ${...} ref or a literal
    symbol: ${input.topic}
    limit: 10
```
Register the tool in Python so the id resolves:
```python
from agent_composer.tools import register_tool

@register_tool("get_facts")
def get_facts(symbol: str, limit: int = 10) -> list[dict]:
    "Fetch recent facts for a symbol."   # docstring = the description the model sees
    ...
```
Note `tool` uses `tool_id:` + `args:` (not `input:`/`output:`). (`model` —
`kind: model`, `model_id:` — is a parseable kind but the serving seam isn't wired
yet; running one raises.)

### `case` — branching (routes only; no `input:`)
Exactly one branch runs; the others skip (their refs resolve to null). **Join the
branches back with a `|` coalesce.**
```yaml
route:
  kind: case
  on: ${synth.output}          # simple form: match a Literal value
  cases:
    - when: go
      then: go_brief
    - when: no_go
      then: no_go_brief
  else: more_info_brief        # required unless the Literal cases are exhaustive
```
Searched form (first true `when:` wins, no `on:`): `when: "${score.output} >= 0.5"`.
Routing on a `Literal` is **exhaustiveness-checked** — omitting a tag with no
`else:` is a compile error.

### `human_input` — a guaranteed human gate
**Always** suspends and waits for a typed answer (validated against `output:`).
```yaml
approve:
  kind: human_input
  input: { plan: ${draft.output} }    # context the prompt may reference (bare ${plan})
  prompt: |-
    Here is the plan:

    ${plan}

    Approve as-is, or revise? (approve / revise)
  output: Approval                    # a typed answer, e.g. a Literal enum
```

### `wait` — a timed pause
```yaml
settle:
  kind: wait
  until: ${input.as_of}
  # order a downstream node after it with depends_on: [settle]
```

### `call` / `map` — composition over child flows
A child is itself a flow file. `call` runs it once; `map` runs it per list element
(`${item}` is the current element).
```yaml
uses:
  research-one: 03-research-one   # bind an external sibling flow to a local alias

nodes:
  each:
    kind: map
    over: ${input.topics}         # a list[T]
    call: research-one            # node value is list[U]
    parallel: true
    input: { topic: ${item} }     # per-element call args (sink-bind the child's params)
```
`call:` resolves **defs-first, else a `uses:` alias** (an external flow on the
search path, by filename; `alias@v1` adds a version guard). Reference the callee's
object fields downstream as `${each.output.field}`.

## Run-ordering without data (`depends_on` / `runs_after`)
Both gate a node on another **settling** even when no value flows. `depends_on:
[x]` also **co-skips** the dependent if `x` skipped; `runs_after: [x]` orders only
(the dependent still runs). Use these for `wait`, side-effecting tools, etc.

## The three expression contexts (different power)
- **Bindings** (`input:`/`output:` values): `${ref}`, a literal, `:-`/`:?`, `|`.
  **No arithmetic** — transforms belong in nodes.
- **`when:` / `asserts:`**: boolean — `== != < <= > >=`, `in`/`not in`,
  `and`/`or`/`not`, parens, operands may use arithmetic (`+ - * / %`). **No
  function calls.**
- **Prompts**: free text with embedded bare `${name}` (stringified).

> Bindings wire, conditions test, nodes compute.

## Prompts see only LOCAL inputs
Inside a `prompt:` you may reference only names the node declares in its own
`input:` block, written bare (`${name}`). Pool references (`${input.x}`,
`${other.output}`) go in the `input:` block — bind there, then use the local name
in the prompt.

## Effects from inside an agent — `ask_user`
A `tool_calling` agent granted `controls: [ask_user]` can pause to ask the human
**only if the model decides it needs to**, then resume with the answer as the tool
result. For a *guaranteed* gate use `human_input`; for "ask only if needed" use
`ask_user`.

## Validate & run
- **Quick validate** (loads + compiles, no model): `ac run <flow>.yaml` will load
  first; or from Python `load_flow(text, search_paths=[flow_dir])`.
- **Run:** `ac run <flow>.yaml --input k=v [--inputs file.json]`. Missing required
  inputs are prompted; a `human_input`/`wait` pause is resumed interactively.
- A flow with only `code`/`tool` nodes runs with **no provider**; any `agent` node
  needs a provider/model configured (see `docs/installation.md`).

## Authoring checklist
- [ ] `input:` and `output:` are fully typed; every type used is a scalar/form or a `typedefs:` entry.
- [ ] Every node consumes upstream values via `${...}` in its `input:` (the edges are inferred).
- [ ] Every `agent` `output:` is typed — `str`/`Literal[...]` for text, or a record/number/bool/list for structured generation.
- [ ] Every prompt references only the node's own local input names.
- [ ] Each `case` has an `else:` (or its `Literal` cases are exhaustive); branches are joined with `|`.
- [ ] `tool` ids are registered; `code` `module:function` is importable; `call`/`uses:` targets resolve on the search path.
- [ ] No arithmetic in bindings; no function calls in `when:`/`asserts:`.
- [ ] It loads cleanly (`ac run` / `load_flow`) before you wire a model.
