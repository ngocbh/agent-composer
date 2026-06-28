from agent_composer.compile.model import CompiledFlow, Edge, START_ID, END_ID
from tests.engine._fakes import FuncNode


def _base() -> CompiledFlow:
    a = FuncNode("a", lambda i: 1)
    nodes = {"a": a}
    edges = [Edge(id="__start__->a", from_=START_ID, to="a"), Edge(id="a->__end__#0", from_="a", to=END_ID)]
    return CompiledFlow.from_parts(nodes=nodes, edges=edges)


def test_add_subgraph_extends_nodes_edges_wiring():
    flow = _base()
    b = FuncNode("ns/b", lambda i: 2)
    flow.add_subgraph(
        nodes={"ns/b": b},
        edges=[Edge(id="a->ns/b#0", from_="a", to="ns/b", input_group="x")],
        wiring={"ns/b": {"x": "${a.output}"}},
    )
    assert "ns/b" in flow.nodes
    assert flow.wiring["ns/b"] == {"x": "${a.output}"}
    # adjacency updated both directions
    assert any(e.to == "ns/b" for e in flow.incoming("ns/b"))
    assert any(e.to == "ns/b" for e in flow.outgoing("a"))
