# Contributing

Thanks for your interest in Agent Composer. This guide covers local setup and the
conventions we hold contributions to — most importantly, the **docstring style**.

## Development setup

```bash
git clone https://github.com/ngocbh/agent-composer
cd agent-composer
pip install -e ".[all,dev]"
```

The `all` extra pulls in every provider client (Anthropic / OpenAI / Google /
Ollama); `dev` adds the test and build tooling.

## Branching workflow

Never commit a feature straight to `main`. Cut a branch first and work from there:

- **Branch off** `main` for independent work, or off another `dev/...` branch when the
  work builds on an unmerged feature.
- **Name it** `dev/<domain>/<feature>` — `<domain>` is the area it touches (`engine`,
  `cli`, `compose`, `docs`, ...) and `<feature>` is a short kebab-case slug, e.g.
  `dev/engine/loop-until-times` or `dev/cli/chat-repl`.
- **Track it** in [`docs/backlog/BRANCHES.md`](docs/backlog/BRANCHES.md): add a row when
  you open the branch, and remove it when it merges.
- **A feature is finished only once it is merged to `main`** — not when the code is
  written or tests pass on the branch. Record the landing commit in
  [`docs/backlog/DONE.md`](docs/backlog/DONE.md).

```bash
git switch -c dev/engine/loop-until-times   # cut the branch off main
# ... implement, test, commit ...
# open a PR; a feature is done only after it merges to main
```

## Running tests

```bash
pytest
```

## Building the docs

```bash
pip install -e ".[docs]"
mkdocs serve   # live preview at http://127.0.0.1:8000
mkdocs build --strict   # what CI / Read the Docs runs
```

The API reference is generated from docstrings by
[mkdocstrings](https://mkdocstrings.github.io/), so a clear docstring is what
makes the reference useful — see the next section.

## Docstring style

We follow a **HuggingFace-flavored, Google-section** style. It is Google-compatible
(so mkdocstrings renders `Args:` / `Returns:` / `Raises:` into tables) but uses
backtick-quoted types and `*optional*, defaults to ...` markers like the
🤗 Transformers codebase.

**Every argument must be documented**, and the description must explain the
argument's *meaning, shape, and constraints* — not merely restate its type.

### Template

```python
def fn(required, optional=None):
    """
    One-line summary in the imperative mood, ending with a period.

    Optional extended description: the *why*, important behavior, invariants,
    or edge cases a caller must know. Omit if the summary says everything.

    Args:
        required (`type`):
            What it is and what it's *for* — not just its type. State the shape
            (e.g. `dict[node_id -> list[Edge]]`), the allowed values, and any
            constraint the caller must satisfy.
        optional (`type`, *optional*, defaults to `None`):
            Same, plus what the default means when omitted.

    Returns:
        `ReturnType`:
            What the value represents and how to interpret its fields/states.
            (Omit this section entirely for functions that return `None`.)

    Raises:
        `SomeError`:
            The exact condition that triggers it. (Omit if it never raises.)

    Example:
        ```python
        >>> result = fn(required=...)
        >>> result.status
        'succeeded'
        ```
    """
```

### Worked example

```python
def run_flow(loaded, inputs, *, run_id=None, on_event=None):
    """
    Coerce inputs, seed the variable pool, enforce asserts, and drive the flow to a terminal.

    Never raises on a flow failure: a failed, paused, or aborted run is returned as a
    `RunResult` with a non-`"succeeded"` status. A false boundary assert returns a
    `status="failed"` result *before* any node runs.

    Args:
        loaded (`LoadedFlow`):
            A compiled, validated flow from [`load_flow`][agent_composer.load_flow].
            Carries the IR, the declared input schema, and the assert sets.
        inputs (`dict[str, Any]`):
            Run arguments keyed by declared input name. Each value is coerced to its
            declared type; names omitted here fall back to their declared defaults.
        run_id (`str`, *optional*, defaults to `None`):
            Host-injected run id, readable in the flow as `${system.run_id}`. When
            `None`, a fresh id is minted per run.
        on_event (`Callable[[Any], None]`, *optional*, defaults to `None`):
            Called with each engine event as it occurs (`NodeStarted`, `RunSucceeded`,
            `RunPaused`, `RunFailed`, `RunAborted`). Use it for progress reporting.

    Returns:
        `RunResult`:
            Outcome of the run. `status` is one of `"succeeded"`, `"failed"`,
            `"paused"`, or `"aborted"`; `output` is set on success, `pause_reasons`
            and resume handles on a pause.

    Example:
        ```python
        from agent_composer import load_flow, run_flow

        loaded = load_flow(open("hello.yaml").read(), search_paths=["."])
        result = run_flow(loaded, {"name": "Ada"})
        print(result.status, result.output)  # succeeded ...
        ```
    """
```

### Conventions

- **Summary** — one imperative line. Add an extended description only when it
  conveys non-obvious information (the *why*, an invariant, an edge case).
- **Args** — document every argument, always. Type in backticks; for keyword
  arguments add `*optional*, defaults to X`. The description explains *meaning +
  shape + constraints*, not a restatement of the type.
- **Returns** — describe what the value *means* and how to read its fields/states.
  Omit the section for functions that return `None`.
- **Raises** — list only exceptions the function actually raises, with the exact
  triggering condition.
- **Example** — include for public-API symbols; optional for internal helpers.
- **Cross-references** — link other symbols with
  `[name][agent_composer.path.name]`; mkdocstrings turns them into links.
- **Comments vs. docstrings** — docstrings explain *what* a thing is and how to
  use it; inline comments explain *why* a non-obvious line exists.
