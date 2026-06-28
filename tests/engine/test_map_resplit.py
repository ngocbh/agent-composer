"""MAP re-split end-state guard: REF and MAP are two distinct typed drivers.

`kind: call` builds REF's `CallNode` (call once); `kind: map` builds MAP's `MapNode` (map over a
list). Pins the re-split so a future re-collapse into one over-flagged CALL node is caught loudly:
REF stays collapsed-out (no `kind: ref`, no `nodes.ref`); MAP is its own kind + package; `CallNode`
carries no `over`/`parallel`; `MapNode` discriminates by kind (no `over` source on the node).
"""

import importlib

import pytest

from agent_composer.nodes.base import NodeKind


def test_ref_kind_gone_call_and_map_are_the_two_drivers():
    assert not hasattr(NodeKind, "REF")              # REF stays collapsed into CALL
    assert NodeKind.CALL.value == "call"
    assert NodeKind.MAP.value == "map"               # MAP re-split into its own kind
    assert NodeKind.CALL is not NodeKind.MAP


def test_ref_package_gone_call_and_map_packages_exist():
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("agent_composer.nodes.ref")
    importlib.import_module("agent_composer.nodes.call")
    importlib.import_module("agent_composer.nodes.map")


def test_call_node_is_ref_only_map_node_is_distinct():
    from agent_composer.nodes.call import CallNode
    from agent_composer.nodes.map import MapNode
    ref = CallNode("c", flow_id="child", child=object())
    assert ref.kind is NodeKind.CALL
    assert not hasattr(ref, "over") and not hasattr(ref, "parallel")  # REF carries neither
    mp = MapNode("m", flow_id="child", child=object(), parallel=True)
    assert mp.kind is NodeKind.MAP and mp.parallel is True
    assert not hasattr(mp, "over")                    # the SOURCE rides flow.wiring, not the node
