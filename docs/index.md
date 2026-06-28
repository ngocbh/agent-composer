# Agent Compose

**Deterministic workflows of agents.** Agent Compose is a small engine for composing
LLM agents, plain Python code, ML models, and tools into a single runnable *flow*,
described in a Docker-Compose-shaped YAML file. **You decide the structure; the LLMs
fill the leaf boxes** — the human owns the graph, the model never rewrites it at runtime.

A flow is a function: it has a typed `input:`, a graph of `nodes:`, and an `output:`.
The graph between nodes is *inferred* from the `${...}` references — you never draw
edges by hand.

```yaml
# hello.yaml
id: hello
name: hello
input:
  name: str
nodes:
  greet:
    kind: agent
    input:
      name: ${input.name}
    output: str
    prompt: |-
      Write a short, warm one-sentence greeting addressed to ${name}.
output: ${greet.output}
```

```console
$ ac run hello.yaml --input name=Ada
Hello, Ada — it's wonderful to have you here!
```

## Why this shape

- **A flow is a function** — typed inputs in, typed outputs out, nothing hidden. An
  agent is just a flow whose leaf computation happens to be an LLM loop.
- **Flows compose** — a node can *be* another flow, nested to any depth.
- **Pure at the boundary** — a node *returns* its output and the engine *binds* it; a
  node never mutates shared state. Outputs are immutable, typed, serializable values.
- **The structure is fixed by the author** — the LLM fills leaf boxes; it does not
  rewrite the graph. That referential transparency is what makes runs reproducible,
  checkpointable, and resumable.

## Where to go next

<div class="grid cards" markdown>

- :material-download: **[Installation](installation.md)** — `pip install agent-composer`, provider extras, and picking a model.
- :material-console: **[The `ac` CLI](cli.md)** — run a flow from the terminal, supply inputs, resume human pauses.
- :material-file-code: **[Flow syntax](syntax.md)** — the full Compose-YAML reference: types, `${...}` refs, node kinds, `case`, coalesce, asserts.
- :material-lightbulb: **[Examples](examples.md)** — walk through the flows that ship in `examples/`.
- :material-language-python: **[Python API](api.md)** — use the engine as a library (`load_flow` / `run_flow` / `resume_flow`).

</div>
