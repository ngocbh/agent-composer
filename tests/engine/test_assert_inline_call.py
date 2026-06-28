"""An inline `${call}` inside a flow `asserts:` expression.

`${ dbl(n=${input.v}) } >= 0` desugars (the same inline-call machinery, extended to the asserts section) to a
synth `__call_<n>` node + the assert rewritten to `${<synth>.output} >= 0`; the synth node runs in
the flow and the assert (now reading `${X.output}`) is classified post and checked after the run.
"""

from agent_composer.compose import load_flow, run_flow

# An in-file `dbl` def (the assert callee): doubles its int input via the `double` CODE fn.
_DBL_DEF = """
defs:
  dbl:
    input:
      n: int
    nodes:
      x:
        kind: code
        code: tests.engine._compose_codefns:double
        input:
          n: ${input.n}
        output: int
    output: ${x.output}
"""

_FLOW = f"""
id: ai
name: ai
input:
  v: int
{_DBL_DEF}
nodes:
  main:
    kind: code
    code: tests.engine._compose_codefns:double
    input:
      n: ${{input.v}}
    output: int
output: ${{main.output}}
asserts:
  - "${{ dbl(n=${{input.v}}) }} >= 0"
"""


def test_inline_call_in_assert_desugars_to_synth_node():
    loaded = load_flow(_FLOW)
    synth = [nid for nid in loaded.compiled.nodes if nid.startswith("__call_")]
    assert len(synth) == 1  # the inline assert-call became a synth node


def test_inline_call_assert_passes():
    out = run_flow(load_flow(_FLOW), {"v": 5})
    assert out.status == "succeeded"
    assert out.output == 10


def test_inline_call_assert_fails_post():
    out = run_flow(load_flow(_FLOW), {"v": -3})  # dbl(-3) = -6, violates `>= 0`
    assert out.status != "succeeded"
    assert "assert" in (out.error or "").lower()
