"""Unit tests for the CompiledFlow topology model."""

from agent_composer.compile.model import END_ID, START_ID, Edge, CompiledFlow
from agent_composer.nodes.end import EndNode
from agent_composer.nodes.start import StartNode
from tests.engine._fakes import FuncNode


def _nodes(*ids):
    return {i: FuncNode(i, lambda p: {}) for i in ids}


def _with_boundary(nodes: dict) -> dict:
    # inject the real START_ID/END_ID boundary NODES (so `from_parts` roots at START_ID + END_ID
    # is the terminal node, the post-flip model).
    nodes = dict(nodes)
    nodes.setdefault(START_ID, StartNode(START_ID, input_decls=[]))
    nodes.setdefault(END_ID, EndNode.record(END_ID, output_names=[]))
    return nodes


def test_adjacency_and_root():
    nodes = _with_boundary(_nodes("a", "b", "c"))
    edges = [
        Edge("e0", START_ID, "a"),
        Edge("e1", "a", "b"),
        Edge("e2", "a", "c"),
        Edge("e3", "b", END_ID),
    ]
    g = CompiledFlow.from_parts(nodes, edges)
    # the single root is the synthesized START_ID; `a` is its out-edge target.
    assert g.start_id == START_ID
    assert {e.to for e in g.outgoing(START_ID)} == {"a"}
    assert {e.to for e in g.outgoing("a")} == {"b", "c"}
    assert [e.from_ for e in g.incoming("b")] == ["a"]
    assert g.terminal_id == END_ID


def test_diamond_incoming():
    nodes = _nodes("a", "b", "c", "d")
    edges = [
        Edge("e0", START_ID, "a"),
        Edge("e1", "a", "b"),
        Edge("e2", "a", "c"),
        Edge("e3", "b", "d"),
        Edge("e4", "c", "d"),
        Edge("e5", "d", END_ID),
    ]
    g = CompiledFlow.from_parts(nodes, edges)
    assert {e.from_ for e in g.incoming("d")} == {"b", "c"}


def test_edge_input_group():
    tagged = Edge(id="e0", from_="a", to="b", input_group="x")
    assert tagged.input_group == "x"
    untagged = Edge(id="e1", from_="a", to="b")
    assert untagged.input_group is None
    legacy = Edge("e2", START_ID, "a")
    assert legacy.input_group is None


def test_compiled_flow_wiring_field_threads_and_defaults():
    # CompiledFlow carries flow-owned wiring (dict[node_id][param] -> source). Default {}.
    nodes = _nodes("a")
    edges = [Edge("e0", START_ID, "a"), Edge("e1", "a", END_ID)]
    g = CompiledFlow.from_parts(nodes, edges, wiring={"a": {"x": "${input.x}"}})
    assert g.wiring == {"a": {"x": "${input.x}"}}
    assert CompiledFlow.from_parts(nodes, edges).wiring == {}


def test_edge_optional_defaults_false_and_roundtrips():
    assert Edge(id="a->b#0", from_="a", to="b", input_group="x").optional is False
    e = Edge(id="a->b#0", from_="a", to="b", input_group="x", optional=True)
    assert e.optional is True


_OPTIONAL_EDGE_FLOW = """
id: opt
name: opt
input:
  seed: float
nodes:
  a:
    kind: code
    code: tests.engine._compose_codefns:score
    input:
      seed: ${input.seed}
    output: float
  hard:
    kind: code
    code: tests.engine._compose_codefns:cautious
    input:
      v: ${a.output}
    output: str
  soft:
    kind: code
    code: tests.engine._compose_codefns:cautious
    input:
      v: ${a.output:-null}
    output: str
output: ${hard.output}
"""


def test_data_edge_optional_reflects_binding_escape():
    from agent_composer.compose import load_flow

    flow = load_flow(_OPTIONAL_EDGE_FLOW).compiled
    by_to = {e.to: e for e in flow.edges if e.input_group == "v"}
    assert by_to["hard"].optional is False  # plain ref -> required
    assert by_to["soft"].optional is True   # `:-null` escape -> optional


_CASE_ESCAPE_FLOW = """
id: ce
name: ce
input:
  seed: float
nodes:
  a:
    kind: code
    code: tests.engine._compose_codefns:score
    input:
      seed: ${input.seed}
    output: float
  gate:
    kind: case
    cases:
      - when: "${a.output:-0} >= 1"
        then: hot
    else: cold
  hot:
    kind: code
    code: tests.engine._compose_codefns:cautious
    input:
      seed: ${input.seed}
    output: str
  cold:
    kind: code
    code: tests.engine._compose_codefns:cautious
    input:
      seed: ${input.seed}
    output: str
output: ${gate.output}
"""


def test_case_condition_escape_marks_optional():
    from agent_composer.compose import load_flow

    flow = load_flow(_CASE_ESCAPE_FLOW).compiled
    a_to_gate = [e for e in flow.edges if e.from_ == "a" and e.to == "gate"]
    assert len(a_to_gate) == 1
    assert a_to_gate[0].optional is True  # `${a.output:-0}` in when: -> optional gate input
