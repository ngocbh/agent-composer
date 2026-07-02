"""End-to-end `while:` loop runs (Ollama-free, pure-CODE body).

The loop carries `{n, exited}`, runs the body `bump` (`{n, exited} -> {n: n+1, exited: n+1>=3}`)
while `not ${exited}`, and terminates when the predicate goes false. Covers the multi-iteration
happy path, the turn-0 (0-iteration) case (seed already satisfies exit), the max-exceeded
runaway guard, and the error boundary — a `while:` predicate that raises at runtime and a
node-budget blowup driven from `_loop_step` both become failed runs, never uncaught escapes.
"""

from agent_composer.compose.loader import load_flow
from agent_composer.compose.run import resume_command, resume_flow, run_flow


COUNTER = """
id: counter
name: counter
defs:
  bump:
    input:
      n: int
      exited: bool
    nodes:
      step:
        kind: code
        code: tests.engine._compose_codefns:loop_bump
        input:
          n: ${input.n}
          exited: ${input.exited}
        output:
          n: int
          exited: bool
    output: ${step.output}
nodes:
  loop:
    kind: loop
    call: bump
    input:
      n: 0
      exited: false
    while: not ${exited}
    max: 10
output: ${loop.output}
"""

# Seed already satisfies exited: true -> 0 body runs, seed committed unchanged.
TURN0 = COUNTER.replace("exited: false", "exited: true")
# max: 2 (< the 3 iterations the body needs) -> the runaway guard fires.
MAXED = COUNTER.replace("max: 10", "max: 2")


def test_while_loop_runs_until_predicate_false():
    result = run_flow(load_flow(COUNTER), {})
    assert result.status == "succeeded"
    assert result.output == {"n": 3, "exited": True}


def test_while_loop_zero_iterations_commits_seed():
    result = run_flow(load_flow(TURN0), {})
    assert result.status == "succeeded"
    assert result.output == {"n": 0, "exited": True}   # seed committed unchanged; 0 body runs


def test_while_loop_max_exceeded_fails_run():
    result = run_flow(load_flow(MAXED), {})
    assert result.status != "succeeded"
    # Assert the runaway guard fired specifically — not just any error mentioning "max"
    # (a `MAX_TOTAL_NODES` budget blowup also contains "max"). The guard message is
    # `loop 'loop' exceeded max (2)`; the budget error says "exceeded node budget".
    assert "exceeded max" in (result.error or "")
    # And confirm the located error type reaches the RunFailed event.
    error_types = {getattr(e, "error_type", None) for e in result.events}
    assert "LoopMaxExceeded" in error_types


# The chat-shaped slice: a body that PAUSES each turn on a `human_input` leaf, folds the
# delivered message into the carried {messages, exited} record, and loops until the human
# types "bye". Drives run() -> paused -> resume -> paused -> ... -> succeeded in-process.
LOOP_CHAT = """
id: chat
name: chat
defs:
  chat_turn:
    input:
      messages: list[str]
    nodes:
      ask:
        kind: human_input
        prompt: "your message"
        output: str
      fold:
        kind: code
        code: tests.engine._compose_codefns:chat_fold
        input:
          messages: ${input.messages}
          msg: ${ask.output}
        output:
          messages: list[str]
          exited: bool
    output: ${fold.output}
nodes:
  loop:
    kind: loop
    call: chat_turn
    input:
      messages: []
      exited: false
    while: not ${exited}
    max: 100
output: ${loop.output}
"""


def test_loop_body_pauses_and_resumes_each_turn():
    loaded = load_flow(LOOP_CHAT)
    # Turn 1: the body's human_input leaf parks the run.
    r1 = run_flow(loaded, {})
    assert r1.status == "paused"
    assert len(r1.pause_reasons) == 1
    # Deliver "hi" -> body END fires -> _loop_step clones the next iteration -> pauses again.
    r2 = resume_flow(loaded, engine=r1.engine,
                     commands=[resume_command(loaded, r1.pause_reasons[0], "hi")])
    assert r2.status == "paused"
    # Deliver "bye" -> fold sets exited=true -> predicate false -> the run succeeds.
    r3 = resume_flow(loaded, engine=r2.engine,
                     commands=[resume_command(loaded, r2.pause_reasons[0], "bye")])
    assert r3.status == "succeeded", r3.error
    assert r3.output == {"messages": ["hi", "bye"], "exited": True}


# A loop that is NOT the terminal node: its committed record feeds a downstream code node.
# Guards that `_loop_step` commits under the spawner id AND fires the spawner's out-edges
# (the terminate -> commit -> advance tail), not just that a terminal loop returns a value.
DOWNSTREAM = COUNTER.replace(
    "output: ${loop.output}",
    """  after:
    kind: code
    code: tests.engine._compose_codefns:double
    input:
      n: ${loop.output.n}
    output: int
output: ${after.output}""",
)


def test_loop_feeding_downstream_node_commits_and_advances():
    result = run_flow(load_flow(DOWNSTREAM), {})
    assert result.status == "succeeded", result.error
    assert result.output == 6          # loop ends at n=3; double(3) = 6


# The `while:` predicate is evaluated OUTSIDE eval_node's try/except (in `_loop_step` for
# iterations >= 1). A predicate that raises at runtime must become a FAILED run, never an
# uncaught escape from run(). Here the predicate divides by the carried `n` (`10 / ${n} > 0`)
# and the body counts n down: the seed pre-check (n=2) and iteration-0 check (n=1) pass, then
# iteration-1's check divides by 0 -> the predicate raises inside `_loop_step`.
PREDICATE_RAISES = """
id: pred-raise
name: pred_raise
defs:
  down:
    input:
      n: int
    nodes:
      step:
        kind: code
        code: tests.engine._compose_codefns:loop_countdown
        input:
          n: ${input.n}
        output:
          n: int
    output: ${step.output}
nodes:
  loop:
    kind: loop
    call: down
    input:
      n: 2
    while: 10 / ${n} > 0
    max: 10
output: ${loop.output}
"""


def test_while_loop_predicate_runtime_error_fails_run():
    # Must NOT raise out of run_flow; the predicate's division-by-zero on iteration 1 is
    # converted to a located run failure at the loop's `while:`.
    result = run_flow(load_flow(PREDICATE_RAISES), {})
    assert result.status != "succeeded"
    assert "division by zero" in (result.error or "")


def test_loop_budget_exceeded_in_step_fails_run(monkeypatch):
    # The node-budget guard inside `_grow_loop` raises a RuntimeError; when that grow is
    # driven from `_loop_step` (iteration >= 1) it must become a failed run, not an uncaught
    # escape. The COUNTER flow adds 3 nodes/iteration off a base of 3 (iter0 -> 6, iter1 -> 9),
    # so a budget of 6 lets iteration 0 grow (via the already-wrapped enqueue path) and trips
    # iteration 1 inside `_loop_step` — exercising the `_loop_step` boundary specifically.
    import agent_composer.runtime.engine as engine_mod

    monkeypatch.setattr(engine_mod, "MAX_TOTAL_NODES", 6)
    result = run_flow(load_flow(COUNTER), {})
    assert result.status != "succeeded"
    assert "node budget" in (result.error or "")

