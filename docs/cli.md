# The `ac` CLI

`ac` runs a flow file: it loads the YAML, gathers the inputs, drives the flow to
a terminal state, and prints the output.

```console
ac run FLOW.yaml [--input k=v]... [--inputs inputs.json] [--quiet]
```

## Supplying inputs

A flow declares typed `input:` fields. You can supply them three ways, and they
layer in this order (later overrides earlier):

1. **`--inputs file.json`** — a JSON object of `{ "key": value, ... }`.
2. **`--input k=v`** — one input, repeatable. Values arrive as strings and are
   coerced to each input's declared type at the run boundary.
3. **Interactive prompt** — any *required* input still missing is prompted for.

```console
# all from flags
ac run examples/decision-brief.yaml --input question="Adopt a monorepo?" --input audience="execs"

# from a JSON file, with one override
ac run flow.yaml --inputs base.json --input audience="execs"

# supply nothing — get prompted for each required input
ac run examples/hello.yaml
```

### The interactive prompt

When a required input is missing, `ac` prompts for it. The widget follows the
declared type:

- a `bool` input → a yes/no confirm,
- a `Literal[...]` enum → a select list of the allowed tags,
- anything else → a free-text entry.

Required inputs are marked with a `*`. An optional input left blank is skipped
(its default applies). Cancelling a prompt (Ctrl-C / Esc) cancels the run.

!!! note
    The prompt needs a real terminal (TTY). In a non-interactive context
    (a CI job, a piped command, `srun` without a pty) supply every required
    input via `--input` / `--inputs` instead, or the run will abort.

## Interactive resume (pauses)

A flow can suspend mid-run — at a `human_input` node, a timed `wait`, or when a
`tool_calling` agent calls the `ask_user` control. `ac` resumes such a run
**interactively**: each pause prints its prompt and asks for the awaited value,
then the run continues. This repeats until the flow reaches a terminal state.

```console
ac run examples/human-approval.yaml --input task="Plan a team offsite"
#   → draft is written
#   → CLI pauses: "Approve it as-is, or send it back to be revised? (approve / revise)"
#   → you type: approve
#   → run continues to completion and prints the kickoff message
```

A timed `wait` asks whether to release the wait now. An external-event pause
can't be satisfied from the CLI and leaves the run paused.

## Output and progress

- The terminal output is rendered as Markdown when it is a non-empty string,
  otherwise printed as-is (e.g. a multi-field object).
- Per-node progress (`→ node_id`) is printed to **stderr** as the flow advances.
  Pass `--quiet` / `-q` to suppress it.

## Exit codes

| Status | Exit code |
|--------|-----------|
| Flow succeeded | `0` |
| Flow failed | `1` (error printed to stderr) |
| Run paused and resume was cancelled | `1` |
| Run cancelled at the input prompt | `1` |

## Next

- [Flow syntax](syntax.md) — write your own flows.
- [Examples](examples.md) — walk the shipped flows.
