"""Round-trip tests for the Expansion descriptor union.

These descriptors are pure durability metadata appended to RunCheckpoint.expansions; the
restore-side replay (_replay_expansions) is exercised elsewhere. These verify the closed sum
types themselves round-trip cleanly and the discriminator is load-bearing.
"""

import pytest
from pydantic import TypeAdapter, ValidationError

from agent_composer.suspension.expansions import (
    AgentExpansion,
    AgentSegment,
    CallExpansion,
    Expansion,
    MapExpansion,
)


def test_call_expansion_round_trip() -> None:
    desc = CallExpansion(spawner_id="analyze", record={"x": 1}, children=[])
    restored = CallExpansion.model_validate_json(desc.model_dump_json())
    assert restored == desc


def test_map_expansion_round_trip() -> None:
    desc = MapExpansion(
        spawner_id="each",
        records=[{"i": 0}, {"i": 1}],
        children_per_element=[[], []],
    )
    restored = MapExpansion.model_validate_json(desc.model_dump_json())
    assert restored == desc


def test_agent_expansion_round_trip() -> None:
    # hi_desc/resume_desc shapes mirror nodes/agent/modes/tool_calling.py:110-126.
    hi_desc = {
        "kind": "human_input",
        "node_id": "agent/hi#0",
        "prompt": "What next?",
        "slot": None,
    }
    resume_desc = {
        "kind": "resume_agent",
        "memo": {"turns": 2},
        "iterations": 2,
        "pending": [],
        "answer": None,
        "llm_config": {"model": "claude-3-5"},
        "tools": ["search"],
        "controls": {"max_iters": 10},
        "mode": "tool_calling",
    }
    seg = AgentSegment(hi_desc=hi_desc, resume_desc=resume_desc, children=[])
    desc = AgentExpansion(spawner_id="agent", segments=[seg])
    restored = AgentExpansion.model_validate_json(desc.model_dump_json())
    assert restored == desc


def test_discriminated_union_round_trip_mixed_list() -> None:
    items: list[Expansion] = [
        CallExpansion(spawner_id="a", record={"k": "v"}, children=[]),
        MapExpansion(
            spawner_id="b",
            records=[{"i": 0}],
            children_per_element=[[]],
        ),
        AgentExpansion(spawner_id="c", segments=[]),
    ]
    adapter = TypeAdapter(list[Expansion])
    raw = adapter.dump_python(items)
    restored = adapter.validate_python(raw)
    assert restored == items

    # Tamper with the discriminator → validation must fail.
    raw[0]["type"] = "bogus_kind"
    with pytest.raises(ValidationError):
        adapter.validate_python(raw)


def test_call_expansion_record_round_trip_preserves_primitives() -> None:
    record = {
        "s": "hello",
        "i": 42,
        "f": 3.14,
        "b": True,
        "n": None,
        "l": [1, 2, "three"],
        "d": {"nested": {"deep": [None, "x"]}},
    }
    desc = CallExpansion(spawner_id="p", record=record, children=[])
    restored = CallExpansion.model_validate_json(desc.model_dump_json())
    for k, v in record.items():
        assert restored.record[k] == v


def test_top_level_reexports() -> None:
    """Expansion descriptor types re-exported from the suspension package."""
    from agent_composer.suspension import (
        AgentExpansion,
        AgentSegment,
        CallExpansion,
        Expansion,
        MapExpansion,
    )

    # Smoke: the Expansion union resolves and accepts each variant via assignment.
    items: list[Expansion] = [
        CallExpansion(spawner_id="a", record={}, children=[]),
        MapExpansion(spawner_id="b", records=[], children_per_element=[]),
        AgentExpansion(spawner_id="c", segments=[]),
    ]
    assert len(items) == 3
    assert AgentSegment is not None
