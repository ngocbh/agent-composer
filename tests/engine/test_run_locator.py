"""Flow-level failures carry a `SourceSpan` on `RunResult.locator`.

A post-terminal assert (`${id.output} ...`) sets an `assert` locator; an input-coercion
failure at the boundary sets an `input_decl` locator (Step 8). Both flow-level paths have
no node behind them, so the locator rides the `RunResult`, not a `NodeFailed`.
"""

from pathlib import Path

from agent_composer.compose import load_flow, run_flow

_ERRORS = Path(__file__).resolve().parents[1] / "seeds" / "errors"


def test_post_assert_sets_run_result_locator():
    text = (_ERRORS / "e19-false-post-assert.yaml").read_text()
    result = run_flow(load_flow(text), {"topic": "X"})
    assert result.status == "failed"
    assert result.locator is not None and result.locator.kind == "assert"
    assert result.locator.node is None
    assert result.locator.key == "${calc.output} > 100"


def test_input_coercion_sets_input_decl_locator():
    text = (_ERRORS / "e08-input-type-mismatch.yaml").read_text()
    result = run_flow(load_flow(text), {"topic": "X", "window": "soon"})
    assert result.status == "failed"
    assert result.locator is not None and result.locator.kind == "input_decl"
    assert result.locator.node is None
    assert result.locator.key == "window"


def test_boundary_assert_sets_assert_locator():
    text = (_ERRORS / "e18-false-boundary-assert.yaml").read_text()
    result = run_flow(load_flow(text), {"window": -5})
    assert result.status == "failed"
    assert result.locator is not None and result.locator.kind == "assert"
    assert result.locator.node is None
    assert result.locator.key == "${input.window} > 0"

