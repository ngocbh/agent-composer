"""disposition predicate: veto (control edges) + per-input data groups.

`disposition(node) -> 'ready' | 'wait' | 'dead'` is the single source of truth for both
the run path (`is_node_ready`) and the skip path (`engine._skip_edge`).
"""

from agent_composer.compile.model import CompiledFlow, Edge, NodeState
from agent_composer.runtime.state_manager import StateManager
from tests.engine._fakes import FuncNode


def _leaf(i: str) -> FuncNode:
    return FuncNode(i, lambda p: {})  # disposition reads only edges; any Node placeholder works


def _sm(node_ids: set[str], edges: list[Edge]) -> StateManager:
    nodes = {i: _leaf(i) for i in node_ids}
    return StateManager(CompiledFlow(nodes=nodes, edges=edges))


# --- VETO: a control edge hard-gates --------------------------------------- #


def test_veto_control_skipped_overrides_taken_data():
    edges = [Edge("g->x#0", "g", "x", source_handle="x"),
             Edge("u->x#0", "u", "x", input_group="v")]
    sm = _sm({"x"}, edges)
    sm.mark_edge("g->x#0", NodeState.SKIPPED)
    sm.mark_edge("u->x#0", NodeState.TAKEN)
    assert sm.disposition("x") == "dead"


def test_veto_control_taken_with_data_taken_is_ready():
    edges = [Edge("g->x#0", "g", "x", source_handle="x"),
             Edge("u->x#0", "u", "x", input_group="v")]
    sm = _sm({"x"}, edges)
    sm.mark_edge("g->x#0", NodeState.TAKEN)
    sm.mark_edge("u->x#0", NodeState.TAKEN)
    assert sm.disposition("x") == "ready"


def test_veto_control_unknown_waits():
    edges = [Edge("g->x#0", "g", "x", source_handle="x")]
    sm = _sm({"x"}, edges)  # UNKNOWN by default
    assert sm.disposition("x") == "wait"


# --- per-input data readiness ----------------------------------------- #


def test_required_data_group_skipped_co_skips():
    edges = [Edge("a->e#0", "a", "e", input_group="base"),
             Edge("b->e#0", "b", "e", input_group="take")]
    sm = _sm({"e"}, edges)
    sm.mark_edge("a->e#0", NodeState.TAKEN)
    sm.mark_edge("b->e#0", NodeState.SKIPPED)
    assert sm.disposition("e") == "dead"


def test_optional_group_skipped_is_ready():
    edges = [Edge("a->e#0", "a", "e", input_group="base"),
             Edge("b->e#0", "b", "e", input_group="take", optional=True)]
    sm = _sm({"e"}, edges)
    sm.mark_edge("a->e#0", NodeState.TAKEN)
    sm.mark_edge("b->e#0", NodeState.SKIPPED)
    assert sm.disposition("e") == "ready"


def test_coalesce_one_taken_is_ready():
    edges = [Edge("a->j#0", "a", "j", input_group="r"),
             Edge("b->j#0", "b", "j", input_group="r")]
    sm = _sm({"j"}, edges)
    sm.mark_edge("a->j#0", NodeState.TAKEN)
    sm.mark_edge("b->j#0", NodeState.SKIPPED)
    assert sm.disposition("j") == "ready"


def test_pure_data_diamond_waits_then_ready():
    edges = [Edge("a->j#0", "a", "j", input_group="p"),
             Edge("b->j#0", "b", "j", input_group="q")]
    sm = _sm({"j"}, edges)
    sm.mark_edge("a->j#0", NodeState.TAKEN)
    assert sm.disposition("j") == "wait"
    sm.mark_edge("b->j#0", NodeState.TAKEN)
    assert sm.disposition("j") == "ready"


def test_no_incoming_is_ready():
    sm = _sm({"r"}, [])
    assert sm.disposition("r") == "ready"


# --- multi-gate-source: OR over control edges ------------------------------ #


def test_multi_gate_one_taken_one_skipped_is_ready():
    edges = [Edge("g1->x#0", "g1", "x", source_handle="x"),
             Edge("g2->x#0", "g2", "x", source_handle="x")]
    sm = _sm({"x"}, edges)
    sm.mark_edge("g1->x#0", NodeState.TAKEN)
    sm.mark_edge("g2->x#0", NodeState.SKIPPED)
    assert sm.disposition("x") == "ready"


def test_multi_gate_both_skipped_is_dead():
    edges = [Edge("g1->x#0", "g1", "x", source_handle="x"),
             Edge("g2->x#0", "g2", "x", source_handle="x")]
    sm = _sm({"x"}, edges)
    sm.mark_edge("g1->x#0", NodeState.SKIPPED)
    sm.mark_edge("g2->x#0", NodeState.SKIPPED)
    assert sm.disposition("x") == "dead"


def test_partial_control_skipped_plus_unknown_waits():
    edges = [Edge("g1->x#0", "g1", "x", source_handle="x"),
             Edge("g2->x#0", "g2", "x", source_handle="x")]
    sm = _sm({"x"}, edges)
    sm.mark_edge("g1->x#0", NodeState.SKIPPED)  # g2->x#0 stays UNKNOWN
    assert sm.disposition("x") == "wait"


# --- ORDERING: depends_on (co-skip) vs runs_after (pure ordering) -------- #


def test_depends_on_source_taken_clears():
    # fetch depends_on warm_cache (no data); warm_cache TAKEN -> fetch ready.
    edges = [Edge("w~>f#0", "w", "f", ordering=True, optional=False)]
    sm = _sm({"f"}, edges)
    sm.mark_edge("w~>f#0", NodeState.TAKEN)
    assert sm.disposition("f") == "ready"


def test_depends_on_source_unknown_waits():
    edges = [Edge("w~>f#0", "w", "f", ordering=True, optional=False)]
    sm = _sm({"f"}, edges)  # UNKNOWN -> gate on the source settling
    assert sm.disposition("f") == "wait"


def test_depends_on_source_skipped_co_skips():
    # the co-skip semantic: warm_cache SKIPPED -> fetch is dead (skip-floods).
    edges = [Edge("w~>f#0", "w", "f", ordering=True, optional=False)]
    sm = _sm({"f"}, edges)
    sm.mark_edge("w~>f#0", NodeState.SKIPPED)
    assert sm.disposition("f") == "dead"


def test_runs_after_source_skipped_still_runs():
    # the pure-ordering semantic: source SKIPPED -> the dependent still runs.
    edges = [Edge("w~>f#0", "w", "f", ordering=True, optional=True)]
    sm = _sm({"f"}, edges)
    sm.mark_edge("w~>f#0", NodeState.SKIPPED)
    assert sm.disposition("f") == "ready"


def test_runs_after_source_unknown_waits():
    edges = [Edge("w~>f#0", "w", "f", ordering=True, optional=True)]
    sm = _sm({"f"}, edges)
    assert sm.disposition("f") == "wait"


def test_depends_on_and_data_edge_both_gate():
    # an ordering edge does NOT join the data co-skip groups: a real data edge plus a
    # satisfied depends_on -> ready; a skipped depends_on -> dead regardless of data.
    edges = [Edge("p->f#0", "p", "f", input_group="x"),
             Edge("w~>f#0", "w", "f", ordering=True, optional=False)]
    sm = _sm({"f"}, edges)
    sm.mark_edge("p->f#0", NodeState.TAKEN)
    sm.mark_edge("w~>f#0", NodeState.TAKEN)
    assert sm.disposition("f") == "ready"


def test_multi_depends_on_any_skipped_is_dead():
    # AND semantics: depends_on [a, b], one skipped -> dead.
    edges = [Edge("a~>f#0", "a", "f", ordering=True, optional=False),
             Edge("b~>f#0", "b", "f", ordering=True, optional=False)]
    sm = _sm({"f"}, edges)
    sm.mark_edge("a~>f#0", NodeState.TAKEN)
    sm.mark_edge("b~>f#0", NodeState.SKIPPED)
    assert sm.disposition("f") == "dead"
