# TODO

Immediate / near-term, **decided** work. **Maintaining this file is the highest-priority
rule** (see CLAUDE.md → "Zeroth rule").

This backlog is split three ways:
- **TODO.md** (here) — immediate or near-future, decided + actionable.
- [**DEFER.md**](DEFER.md) — open questions / trade-offs we're thinking about but haven't decided.
- [**FUTURE.md**](FUTURE.md) — big, directionally-decided plans out of near-term scope (v2-scale).

**Convention**
- `- [ ] open item` — still to do.
- `- [x] ~~done item~~ -- <short-commit-hash>` — on completion: tick, strike, append `--` with the
  **exact short commit hash** (commit the work first, then record the hash in the next commit).

Add an item the moment you notice work for later, or whenever the user defers something. When in
doubt about which file: decided+soon → here; undecided → DEFER; big+later → FUTURE.

This directory (`docs/backlog/`) is the project roadmap, tracked in git and published in the doc site
under "Roadmap".

---

## Publish to PyPI

- [ ] (optional) Run `twine upload` from `dist/` to publish the built wheel/sdist to PyPI.

## Engine

- [ ] **Pooled durable resume — make `resume()` drive-mode-aware + checkpoint `num_workers`.**
  `resume()` hardcodes the serial drain (`runtime/engine.py:389`); it should pick serial vs pooled
  exactly as `run()` does (spawn workers + dispatch + join), so a checkpointed run is resumable with
  ANY worker count. Sound because workers are pure executors and the single-writer dispatcher owns all
  mutation — correctness is worker-count-independent. **Persist `num_workers` in `RunCheckpoint`**
  (snapshot captures `engine.num_workers`); `restore()` defaults to the checkpointed count, but
  `restore(flow, ckpt, num_workers=N)` **overrides** it.

- [ ] **(low) `pause_reasons = paused[0].reasons` collapses a simultaneous multi-node pause** — only
  the first paused node's reasons surface. Rare (needs two nodes pausing in one step). Fix when a real
  multi-node pause flow exists.

- [ ] **Locate the unknown AGENT mode/control `LoadError`.** `build_leaf_node` surfaces an invalid
  `mode:`/`controls:` as `LoadError(f"node {desc.id!r}: {exc}")` (`compose/build.py:167`) with **no
  `.line`**, so the error can't point the author at the offending YAML line. Thread the node's source
  line onto the raised `LoadError` (the descriptor knows its node id; the parser has the line). Narrower
  and easier than the general "defs-internal error line-mapping" item in DEFER.

- [ ] \ngoc{add options to human input so claude can compose question and also options similar to claude. claude we should have an option to let the agent to redesign or write the question/options depending on the inputs/context. Do human input node should have an option to receive context and option to ask LLM to redesign the questions/options. There are should me multiple questions as well.

- [ ] **Compact mode — a single-node flow authored inline (flow *is* the node).** Let an author
  collapse the common "one flow, one node" case so they don't have to write a `nodes:` map + a
  redundant `output: ${greet.output}` wiring step. Instead of the full form, allow the flow's
  top-level body to carry the node's fields directly — e.g. a flow whose top level is
  `kind: agent` / `input:` / `output:` / `prompt:` is parsed as a flow with a single implicit node
  whose output is the flow output. The parser detects the compact shape (a node `kind:` at flow top
  level, no `nodes:` map) and desugars it into the canonical one-node flow before compile, so the IR
  and engine are unchanged. **Decided:** the compact form may carry an optional `id:` for the node;
  when omitted, fall back to an implicit default id. Still open: how flow `input:` maps onto the
  node's `input:`, and which node kinds are allowed in compact form. Update `docs/syntax.md` + the
  `composing-agents` skill (with a compact-form template) in the same change.

## LLM config — cascade + per-node opt-out + CLI override

**Decided shape** (promoted from DEFER): `llm_config` propagates parent→child as a per-field
**fill-the-gap** cascade (most-specific wins); flow-level config is **optional**; a node can opt out of
the whole cascade with `inherit: false`; the CLI can inject a config as the outermost layer.

Resolve each agent node's **effective** config at compile/expand time so nodes stay pure (the effective
dict is baked onto the node — no runtime pool reads). Precedence, most→least specific:
**node → enclosing (sub)flow → parent flow(s) → top flow → CLI-passed config → global runtime defaults.**

- [x] ~~**Flow-level `llm_config` section**~~ — allow a top-level `llm_config:` on a flow (and on a
  subflow), parsed onto the flow shape (`compose/parser.py`, `compose/shapes.py`). Optional — absent is
  fine, no loud load error. -- 4ed6f24
- [x] ~~**Cascade resolution (fill-the-gap, per field, most-specific wins).**~~ Build each agent's effective
  config by merging the layers above; threads through `call`/`uses:` subflow expansion
  (`compile/expand.py`) so a child inherits the enclosing/parent flow config for fields it leaves unset. -- ddfc066
- [x] ~~**`inherit: false` on an agent's `llm_config`**~~ — opt the node out of the **entire** cascade: use
  only its own dict over global runtime defaults. Whole-node only (per-field locking deferred → see
  DEFER). Parser field → `AgentNode`; short-circuits cascade resolution. -- 5da4878
- [x] ~~**CLI flags supply the flow-level config**~~ — `ac run --provider <p> --model <m>` (mirrors the
  `AGENT_COMPOSER_DEFAULT_*` env vars). The flags don't override `_settings.py` directly; they **supply
  an outermost `llm_config` layer** that **propagates via the cascade** to every agent that sets none.
  Precedence is just the cascade (fill-the-gap, most-specific-wins): a node's own `llm_config` wins,
  `inherit:false` nodes ignore it, and an unset flag falls back to the env-var default. **Open edge:** if
  a flow *authors its own* top-level `llm_config:` AND the user passes `--model`, the lean is CLI
  **fills gaps only** (authored flow-level config wins) — not a force-override. Depends on the cascade above. -- d38675f
- [x] ~~**Docs + skills (same change)**~~ — `docs/syntax.md` (flow-level config, `inherit:false`, CLI flag),
  `composing-agents` skill (`reference.md` + a template for flow-level config / opt-out), `engine` skill
  if cascade semantics touch internals. Re-validate touched templates load. -- 4e69909
- [x] ~~**Tests**~~ — gap-fill merge; node field wins over parent; `inherit:false` isolation; CLI injection
  as outermost layer; no-config-anywhere falls back to global runtime defaults. -- 6506c35

## Structured AGENT output — wire the declared shape into generation

**Decided shape** (promoted from DEFER). Parts (a) **declare** `output:` ✓ and (b) **enforce** at the
write boundary ✓ already exist; this builds **(c) generate** — constrain the model to emit the declared
shape. Layered strategy, with the boundary check kept as the final guarantee (defense-in-depth):
generation *tries*, the boundary *enforces*, retry catches the residual.

- [x] ~~**Shape → schema derivation** — convert a node's `output:` `Shape` into a JSON schema / pydantic
  model that `with_structured_output` accepts. Skip a bare scalar `str` (today's text passthrough); apply
  for every other declared shape — records, lists, AND scalar `int`/`float` (structured extraction beats
  text parsing).~~ -- 44d6048
- [x] ~~**`plain` mode: native structured output** — invoke via `model.with_structured_output(schema)`
  instead of the raw string return (`modes/plain.py:22`). The primary path.~~ -- 8cf9d17
- [x] ~~**Boundary parse-retry** — on a write-boundary mismatch, re-invoke with the error appended
  (self-correction), capped at N retries, then fail. The existing (b) check stays the enforcer.~~ -- 0fd5a28
- [x] ~~**Authorable `retries:` field** — let an author set the self-correction cap per agent node
  (`retries: 3`, default 2); threads parser → build → `AgentNode` → `AgentRunContext` →
  `generate_structured(max_retries=...)`.~~ -- 0fd5a28
- [x] ~~**Prompt-injection fallback + capability detection** — for providers/models without native
  structured output, render the schema + "respond with JSON matching this" + parse. Detect support via a
  **capability flag in the model catalog** (explicit, testable), not try/except.~~ -- 6752e6f, dc61c84
- [x] ~~**`tool_calling` mode: structured final answer** — the loop still calls tools mid-run, but the
  FINAL answer turn must emit the declared shape (a forced final "emit" step / `with_structured_output`
  on the synthesis turn). Lands after `plain`.~~ -- bfc31ac
- [x] ~~**Docs + skills (same change)** — `docs/syntax.md` (the `output:` → structured-generation
  contract; remove the "no JSON/structured parse" caveat at `syntax.md:100`), `composing-agents` skill
  (`reference.md` + a typed-output template), `engine` skill if the agent contract notes change.~~ -- 8f876ad
- [x] ~~**Tests** — schema derivation per shape; `plain` native path; boundary-retry on a bad emit;
  prompt-injection fallback for a no-native-support provider; `tool_calling` structured final answer;
  bare-`str` still passes through untouched.~~ -- e4504ce

The **tool** typed-output half stays in DEFER ("Contract gaps") — same theme, separate node kind.

## CLI

- [ ] **Describe inputs when prompting** — the flow `input:` section is `name: TYPE` (or
  `TYPE = default`) with no place for a human description (`InputDecl` in `compose/shapes.py:55` has
  `name`/`type`/`default`/`required`/`shape`, **no `description`**). Two parts: (a) let an author
  attach a per-input description in the YAML and thread it onto `InputDecl`; (b) when the CLI prompts
  for a missing input (`_prompt_missing`, `cli/run.py`), show that description. Required/optional is
  already surfaced (required inputs are starred). **Scope: flow-level inputs only** — node `inputs:` are
  wired from refs, never prompted from a human, so they get no description slot.

- [ ] **`cli/utils.py` helpers** referenced by `llm_clients` comments but not built: `ensure_api_key`
  (interactive key prompt) + `confirm_ollama_endpoint`.

## Tooling

- [ ] **Project-wide pyright not clean / not wired to the env** — `npx pyright src/agent_composerr`
  reports errors, but most are artifacts of pyright not resolving the conda env's site-packages
  (`reportMissingImports` on `pydantic`, cascading into override errors on the pydantic models). Needs:
  point pyright at the project interpreter (`pyrightconfig` / `venvPath`+`venv`), then triage what
  genuinely remains. Undecided whether to gate CI on it — see also DEFER.

## Open bugs / known issues

- [ ] **`ask_user` resume is broken for providers with dashed tool-call ids (e.g. Ollama uuids).**
  When a `tool_calling` agent calls the `ask_user` control, the loop mints a namespaced human-input
  leaf id `__ask#<call_id>` and an answer forward-ref `${__ask#<call_id>.output}`
  (`nodes/agent/modes/tool_calling.py:109,121`). On resume that ref is parsed by `_PATH_RE`
  (`expr/template.py:45` = `^[A-Za-z_][A-Za-z0-9_#/]*...`), which allows `_ # /` but **not `-`**.
  Ollama's `call_id` is a uuid (`adebc542-e4a3-...`), so resume fails with `malformed reference path`.
  Anthropic/OpenAI ids (`toolu_…`/`call_…`, no dashes) happen to pass. **Fix:** sanitize the call_id
  to a path-safe slug when forming `hi_id`/the answer ref (keep the real id only in the pending
  `call_id`/`slot` for the `ToolMessage` match), and add a test using a dashed/uuid call_id. (The
  HUMAN_INPUT node path is unaffected.)
