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


def test_register_adds_unknown_entries():
    sm = _sm()
    e = Edge(id="a->ns/b#0", from_="a", to="ns/b", input_group="x")
    sm.flow.add_subgraph(nodes={"ns/b": FuncNode("ns/b", lambda i: 2)}, edges=[e], wiring={"ns/b": {"x": "${a.output}"}})
    sm.register(node_ids=["ns/b"], edges=[e])
    assert sm.node_state["ns/b"] == NodeState.UNKNOWN
    assert sm.edge_state["a->ns/b#0"] == NodeState.UNKNOWN


def test_disposition_no_keyerror_on_registered_edge():
    sm = _sm()
    e = Edge(id="a->ns/b#0", from_="a", to="ns/b", input_group="x")
    sm.flow.add_subgraph(nodes={"ns/b": FuncNode("ns/b", lambda i: 2)}, edges=[e], wiring={"ns/b": {"x": "${a.output}"}})
    sm.register(node_ids=["ns/b"], edges=[e])
    assert sm.disposition("ns/b") == "wait"     # the new edge is UNKNOWN -> wait, not a KeyError
