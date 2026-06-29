import pytest

from agent_composer.compose.loader import load_flow
from agent_composer.compose.run import resume_command, run_flow, resume_flow
from agent_composer.suspension.commands import DeliverAnswerCommand
from agent_composer.suspension.checkpoint import RunCheckpoint
from agent_composer.suspension.pause import EventAwaited

FLOW = """
id: f
name: f
input:
  settle_at: date
nodes:
  settle:
    kind: wait
    until: ${input.settle_at}
  done:
    kind: code
    depends_on: [settle]
    output: str
    code: tests.seeds.fns:confirm_action
output: ${done.output}
"""


def test_run_flow_pauses_carries_handles():
    loaded = load_flow(FLOW)
    res = run_flow(loaded, {"settle_at": "2026-07-01"})
    assert res.status == "paused"
    assert res.checkpoint is not None
    assert res.engine is not None
    assert len(res.pause_reasons) == 1


def test_resume_via_checkpoint_completes():
    loaded = load_flow(FLOW)
    res = run_flow(loaded, {"settle_at": "2026-07-01"})
    blob = res.checkpoint.dumps()
    ckpt = RunCheckpoint.loads(blob)             # cross-process round-trip
    release = DeliverAnswerCommand(node_id="settle", value=None)   # WAIT release = Output(None)
    res2 = resume_flow(loaded, checkpoint=ckpt, commands=[release])
    assert res2.status == "succeeded"
    assert res2.output == "cancel"               # confirm_action(rec={}) -> "cancel"


def test_resume_via_live_engine_completes():
    loaded = load_flow(FLOW)
    res = run_flow(loaded, {"settle_at": "2026-07-01"})
    release = DeliverAnswerCommand(node_id="settle", value=None)   # WAIT release = Output(None)
    res2 = resume_flow(loaded, engine=res.engine, commands=[release])
    assert res2.status == "succeeded"
    assert res2.output == "cancel"


EFFECTS = """
id: e
name: e
typedefs:
  Approval: Literal[approve, reject]
input:
  settle_at: date
nodes:
  approve:
    kind: human_input
    prompt: "approve? (approve/reject)"
    output: Approval
  gate:
    kind: case
    on: ${approve.output}
    cases:
      - when: approve
        then: settle
    else: abort
  settle:
    kind: wait
    until: ${input.settle_at}
  confirm:
    kind: code
    depends_on: [settle]
    input:
      answer: ${approve.output}
    output: str
    code: tests.seeds.fns:confirm_action
  abort:
    kind: code
    input:
      answer: ${approve.output}
    output: str
    code: tests.seeds.fns:confirm_action
output: ${confirm.output | abort.output}
"""


def test_effects_approve_path():
    loaded = load_flow(EFFECTS)
    r1 = run_flow(loaded, {"settle_at": "2026-07-01"})
    assert r1.status == "paused"                       # at human_input
    r2 = resume_flow(loaded, engine=r1.engine,
                     commands=[DeliverAnswerCommand(node_id="approve", value="approve")])
    assert r2.status == "paused"                       # at the timed wait
    r3 = resume_flow(loaded, engine=r2.engine,
                     commands=[DeliverAnswerCommand(node_id="settle", value=None)])
    assert r3.status == "succeeded"
    assert r3.output == "approve"                      # confirm_action(rec={answer:"approve"})


def test_effects_reject_path():
    loaded = load_flow(EFFECTS)
    r1 = run_flow(loaded, {"settle_at": "2026-07-01"})
    r2 = resume_flow(loaded, engine=r1.engine,
                     commands=[DeliverAnswerCommand(node_id="approve", value="reject")])
    assert r2.status == "succeeded"                    # abort branch, no wait
    assert r2.output == "reject"                       # confirm_action(rec={answer:"reject"})


def test_effects_typed_answer_rejected():
    loaded = load_flow(EFFECTS)
    r1 = run_flow(loaded, {"settle_at": "2026-07-01"})
    r2 = resume_flow(loaded, engine=r1.engine,
                     commands=[DeliverAnswerCommand(node_id="approve", value="maybe")])
    assert r2.status == "failed"            # "maybe" not in Literal[approve,reject]: pool.set rejects,
                                            # guarded -> NodeExecutionError -> RunFailed (resume does NOT crash)


def test_multi_pause_resume_via_resume_command():
    # Drive human_input -> wait entirely through the logical contract: each resume reads
    # the refreshed pause reason and maps it to a command via resume_command (no hardcoded
    # coordinate). Exercises the loop body more than once.
    loaded = load_flow(EFFECTS)
    r1 = run_flow(loaded, {"settle_at": "2026-07-01"})
    assert r1.status == "paused"                         # at human_input "approve"
    cmd1 = resume_command(loaded, r1.pause_reasons[0], "approve")
    r2 = resume_flow(loaded, engine=r1.engine, commands=[cmd1])
    assert r2.status == "paused"                         # now at the wait
    cmd2 = resume_command(loaded, r2.pause_reasons[0], True)
    r3 = resume_flow(loaded, engine=r2.engine, commands=[cmd2])
    assert r3.status == "succeeded"
    assert r3.output == "approve"


def test_resume_command_rejects_non_resumable_reason():
    loaded = load_flow(EFFECTS)
    with pytest.raises(ValueError):
        resume_command(loaded, EventAwaited(), "x")  # external-watcher pause, not host-resumable


def test_resume_command_builds_deliver_for_human_input():
    loaded = load_flow(EFFECTS)
    r1 = run_flow(loaded, {"settle_at": "2026-07-01"})
    cmd = resume_command(loaded, r1.pause_reasons[0], "approve")
    assert isinstance(cmd, DeliverAnswerCommand)               # deliver-as-Output, not a variable patch
    assert cmd.node_id == "approve" and cmd.value == "approve"


def test_full_host_round_trip_human_then_wait():
    loaded = load_flow(EFFECTS)
    r1 = run_flow(loaded, {"settle_at": "2026-07-01"})
    assert r1.status == "paused"                               # at human_input "approve"
    r2 = resume_flow(loaded, engine=r1.engine,
                     commands=[resume_command(loaded, r1.pause_reasons[0], "approve")])
    assert r2.status == "paused"                               # at the timed wait "settle"
    r3 = resume_flow(loaded, engine=r2.engine,
                     commands=[resume_command(loaded, r2.pause_reasons[0], None)])  # WAIT release
    assert r3.status == "succeeded"
    assert r3.output == "approve"


def test_resume_command_does_not_require_node_in_compiled_flow():
    # the parked id may be a live namespaced id that exists only on engine.flow.nodes;
    # resume_command must dispatch on the reason SHAPE, never deref loaded.compiled.nodes.
    from types import SimpleNamespace

    from agent_composer.suspension.pause import HumanInputRequired

    loaded = SimpleNamespace(compiled=SimpleNamespace(nodes={}))   # EMPTY static graph
    reason = HumanInputRequired(prompt="?", node_id="call_sub/w")  # a live namespaced id
    cmd = resume_command(loaded, reason, "x")
    assert isinstance(cmd, DeliverAnswerCommand)
    assert cmd.node_id == "call_sub/w"                              # passed straight through


def test_checkpoint_persists_num_workers_roundtrip():
    """num_workers survives a dumps()->loads() round-trip; absent it would default to 0
    and a pooled resume would silently downgrade to serial."""
    from agent_composer.state.pool import TypedVariablePool
    ckpt = RunCheckpoint(pool=TypedVariablePool(), num_workers=4)
    loaded = RunCheckpoint.loads(ckpt.dumps())
    assert loaded.num_workers == 4


def test_checkpoint_num_workers_defaults_zero():
    from agent_composer.state.pool import TypedVariablePool
    ckpt = RunCheckpoint(pool=TypedVariablePool())
    assert ckpt.num_workers == 0


def test_checkpoint_rejects_pre_6_blob():
    import json
    from agent_composer.state.pool import TypedVariablePool
    raw = json.loads(RunCheckpoint(pool=TypedVariablePool()).dumps())
    raw["version"] = "5.0"                       # force an older version explicitly
    with pytest.raises(ValueError, match="incompatible checkpoint version"):
        RunCheckpoint.loads(json.dumps(raw))
