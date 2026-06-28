"""The `NodeResult` closed sum: Output | Pause | Enqueue.

Three variants only. The FAILED path is `raise` -> engine boundary `NodeFailed` (no `Failure`
variant). `Enqueue` is defined here but produced/interpreted by the composition drivers.
"""

from agent_composer.nodes.base import Enqueue, Output, Pause


def test_output_carries_value_and_handle():
    assert Output(value=3).value == 3
    assert Output(value=3).handle is None
    assert Output(value=None, handle="case_a").handle == "case_a"


def test_pause_carries_reason():
    assert Pause(reason="needs-input").reason == "needs-input"


def test_enqueue_is_defined():
    e = Enqueue(target="child", inputs={"x": 1})
    assert e.target == "child"
    assert e.inputs == {"x": 1}
