from agent_composer.compile.model import CompiledFlow, Edge, NodeState, START_ID, END_ID
from agent_composer.runtime.state_manager import StateManager
from tests.engine._fakes import FuncNode


def _sm() -> StateManager:
    a = FuncNode("a", lambda i: 1)
    flow = CompiledFlow.from_parts(
        nodes={"a": a},
        edges=[Edge(id="__start__->a", from_=START_ID, to="a"), Edge(id="a->__end__#0", from_="a", to=END_ID)],
    )
    return StateManager(flow)


def test_drop_clears_node_and_edge_state():
    # Register two overlay nodes/edges, mark one executing, then drop that one.
    sm = _sm()
    keep = Edge(id="a->ns/keep#0", from_="a", to="ns/keep", input_group="x")
    drop = Edge(id="a->ns/drop#0", from_="a", to="ns/drop", input_group="x")
    sm.flow.add_subgraph(
        nodes={"ns/keep": FuncNode("ns/keep", lambda i: 2), "ns/drop": FuncNode("ns/drop", lambda i: 3)},
        edges=[keep, drop],
        wiring={"ns/keep": {"x": "${a.output}"}, "ns/drop": {"x": "${a.output}"}},
    )
    sm.register(node_ids=["ns/keep", "ns/drop"], edges=[keep, drop])
    sm.add_executing("ns/drop")  # exercise the executing.discard path

    sm.drop(node_ids={"ns/drop"}, edge_ids={"a->ns/drop#0"})

    # dropped id gone from every per-node / per-edge structure
    assert "ns/drop" not in sm.node_state
    assert "ns/drop" not in sm.executing
    assert "a->ns/drop#0" not in sm.edge_state

    # the surviving overlay node/edge is untouched (over-drop guard)
    assert sm.node_state["ns/keep"] == NodeState.UNKNOWN
    assert sm.edge_state["a->ns/keep#0"] == NodeState.UNKNOWN
