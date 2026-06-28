"""`AgentRunContext` carries config-as-data, NOT scratch.

The agent memo now rides as graph data through the `resume_agent` continuation,
not through a `scratch` cap — so `AgentRunContext` no longer has a `.scratch` field; it
carries `llm_config` (config-as-data the continuation forwards)."""

from agent_composer.nodes.agent.modes.common import AgentRunContext


def test_runcontext_carries_config_no_scratch():
    ctx = AgentRunContext(node_id="a", prompt="p", llm_config="CFG")
    assert ctx.llm_config == "CFG"
    assert not hasattr(ctx, "scratch")
