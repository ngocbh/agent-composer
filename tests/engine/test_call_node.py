from types import SimpleNamespace

import pytest

from agent_composer.nodes.base import Enqueue, NodeKind
from agent_composer.nodes.call import CallNode
from agent_composer.nodes.map import MapNode


def _child():
    # a stub baked child: run only reads self.child for the not-baked guard + threads
    # it into Enqueue.target; apply_defaults reads the (empty) child_inputs decls.
    return SimpleNamespace(nodes={}, edges=[], wiring={}, outputs=[])


def test_call_node_is_ref_only():
    ref = CallNode("c", flow_id="child", child=_child())
    assert ref.kind == NodeKind.CALL
    assert not hasattr(ref, "over")                   # REF carries no over/parallel
    assert not hasattr(ref, "parallel")


def test_map_node_kind_and_parallel_fields():
    mp = MapNode("m", flow_id="child", child=_child(), parallel=True)
    assert mp.kind == NodeKind.MAP
    assert mp.parallel is True
    assert not hasattr(mp, "over")                    # the SOURCE rides flow.wiring, not the node
    assert MapNode("d", flow_id="child", child=_child()).parallel is False


def test_call_ref_mode_returns_one_enqueue():
    node = CallNode("c", flow_id="child", child=_child(), child_inputs=[])
    out = node.run({"topic": "ACME"})
    assert isinstance(out, Enqueue)
    assert out.inputs == {"topic": "ACME"} and out.target is node.child


def test_map_returns_list_of_enqueue():
    node = MapNode("m", flow_id="child", child=_child(), child_inputs=[])
    out = node.run({"over": ["ACME", "BETA"]}, bind_item=lambda el: {"topic": el})
    assert isinstance(out, list) and len(out) == 2
    assert [e.inputs for e in out] == [{"topic": "ACME"}, {"topic": "BETA"}]


def test_map_empty_returns_empty_list():
    node = MapNode("m", flow_id="child", child=_child(), child_inputs=[])
    assert node.run({"over": []}, bind_item=lambda el: {"topic": el}) == []


def test_call_unbaked_child_raises():
    node = CallNode("c", flow_id="child", child=None)
    with pytest.raises(RuntimeError, match="not baked"):
        node.run({"topic": "ACME"})


def test_map_unbaked_child_raises():
    node = MapNode("m", flow_id="child", child=None)
    with pytest.raises(RuntimeError, match="not baked"):
        node.run({"over": ["ACME"]}, bind_item=lambda el: {"topic": el})
