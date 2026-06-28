"""`NodeKind.MAP` + `MapNode`: the re-split MAP driver (no caller wired yet).

`MapNode` discriminates by KIND (`NodeKind.MAP`), not an `over` flag — it carries NO `over`
attribute and no `${...}` source on the node; the `over` SOURCE rides `flow.wiring[id]["over"]`
(the engine pre-resolves it into `inputs["over"]` before `run`). `run` returns `list[Enqueue]`,
one per element (empty `over` -> `[]`).
"""

import importlib

from agent_composer.nodes.base import Enqueue, NodeKind
from agent_composer.nodes.map import MapNode


def test_map_node_kind_value():
    assert NodeKind.MAP == "map"
    assert NodeKind.MAP.value == "map"


def test_map_node_carries_no_over_attr():
    n = MapNode("m", flow_id="child", child=object(), parallel=True)
    assert n.parallel is True
    assert n.child is not None
    assert not hasattr(n, "over")          # discriminator is the KIND, not an `over` flag
    assert MapNode("d", flow_id="child", child=object()).parallel is False


def test_map_node_run_fans_out_one_enqueue_per_element():
    child = object()
    n = MapNode("m", flow_id="child", child=child,
                child_inputs=[], child_asserts=None)
    enqs = n.run({"over": [1, 2, 3]}, bind_item=lambda el: {"x": el})
    assert all(isinstance(e, Enqueue) for e in enqs)
    assert [e.target for e in enqs] == [child, child, child]
    assert [e.inputs for e in enqs] == [{"x": 1}, {"x": 2}, {"x": 3}]


def test_map_node_run_empty_over_is_empty_list():
    n = MapNode("m", flow_id="child", child=object(), child_inputs=[])
    assert n.run({"over": []}, bind_item=lambda el: {"x": el}) == []


def test_map_node_kind_exists_and_package_imports():
    assert hasattr(NodeKind, "MAP")
    importlib.import_module("agent_composer.nodes.map")
