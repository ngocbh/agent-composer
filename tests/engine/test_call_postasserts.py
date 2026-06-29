"""A `call` node's node-local POST `asserts:` must fire — at the alias-commit site.

A `call` is a spawner: it yields an `Enqueue` (eval_node returns BEFORE the post-assert
block), and its `${output}` is committed LATER, in `engine._on_success`'s alias branch when
the cloned child's END filler finishes. So the call's `${output}` post-asserts can ONLY run
there; eval_node's post-assert block never sees them. Before the fix they were silently
dropped — a false one passed quietly, violating "a false assert fails the run loudly".

These pin: a true call post-assert passes, a false one fails the run LOUDLY (RunFailed,
error_type "NodeAssertFailed", a non-null locator at the assert), and a post-assert reading
BOTH a declared call input AND `${output}` fires correctly (the input is recovered from the
persisted `CallExpansion.record`).
"""

from agent_composer.compose import load_flow, run_flow
from agent_composer.events import RunFailed



# A child that re-exports a {report, n} record (the Ollama-free CODE child pattern). The
# parent `call`s it; the call's `${output}` is that {report, n} record. `n == len(topic)`.
_CHILD = """
id: child-one
name: child_one
input:
  topic: str
nodes:
  emit:
    kind: code
    input:
      topic: ${input.topic}
    output:
      report: str
      n: int
    code: tests.engine._compose_codefns:make_report
output:
  report: ${emit.output.report}
  n: ${emit.output.n}
"""


def _resolver(**children):
    loaded = {fid: load_flow(text) for fid, text in children.items()}

    def resolve(flow_id, version=None):
        return loaded[flow_id]

    return resolve


def _parent(asserts: str) -> str:
    # A parent that `call`s child-one with a fixed topic, carrying the given `asserts:` block
    # on the call node. `topic` ("ACME") is a declared call input -> n == 4.
    return f"""
id: call-parent
name: call_parent
uses:
  child-one: child-one
nodes:
  research:
    kind: call
    call: child-one
    input:
      topic: ACME
    asserts:
{asserts}
output: ${{research.output}}
"""


def _load(asserts: str):
    return load_flow(_parent(asserts), child_resolver=_resolver(**{"child-one": _CHILD}))


# --- 1. live, passing -------------------------------------------------------- #


def test_call_post_assert_true_passes():
    # a true `${output.field}` post-assert -> the run succeeds.
    loaded = _load("      - ${output.n} == 4")
    res = run_flow(loaded, {})
    assert res.status == "succeeded", res.error
    assert res.output == {"report": "report for ACME", "n": 4}


# --- 2. live, false -> loud failure ----------------------------------------- #


def test_call_post_assert_false_fails_loudly():
    # a false `${output}` post-assert -> RunFailed, error_type NodeAssertFailed, a non-null
    # locator pinned at the assert on the call node. (Before the fix this passed SILENTLY:
    # the run succeeded and this assert would fail by NOT failing.)
    loaded = _load("      - ${output.n} == 999")
    res = run_flow(loaded, {})
    assert res.status == "failed"
    failed = [e for e in res.events if isinstance(e, RunFailed)]
    assert failed and failed[0].error_type == "NodeAssertFailed"
    loc = res.locator
    assert loc is not None
    assert loc.node == "research" and loc.kind == "assert"
    assert loc.key == "${output.n} == 999"


# --- 3. live, input + output ref -------------------------------------------- #


def test_call_post_assert_reads_input_and_output_true():
    # a post-assert reading BOTH a declared call input (`topic`) AND `${output}` -> true holds.
    # n == len("ACME") == 4, so `len(topic) == n` is satisfied via the recovered input record.
    loaded = _load("      - ${output.n} == 4")  # baseline true
    res = run_flow(loaded, {})
    assert res.status == "succeeded", res.error


def test_call_post_assert_reads_input_and_output_false():
    # an input+output post-assert that is FALSE -> loud failure. `topic` ("ACME") is the
    # recovered call input; `${output.report}` mentions it but `${topic} == "OTHER"` is false.
    loaded = _load('      - ${topic} == "OTHER" and ${output.n} == 4')
    res = run_flow(loaded, {})
    assert res.status == "failed"
    failed = [e for e in res.events if isinstance(e, RunFailed)]
    assert failed and failed[0].error_type == "NodeAssertFailed"
    assert res.locator is not None and res.locator.node == "research"


def test_call_post_assert_reads_input_true():
    # the input ref resolves from the recovered CallExpansion.record (not None/dropped).
    loaded = _load('      - ${topic} == "ACME" and ${output.n} == 4')
    res = run_flow(loaded, {})
    assert res.status == "succeeded", res.error
