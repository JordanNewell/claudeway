"""
Consensus strategy tests.

Pure logic — no Anthropic API calls. Uses a stub Swarm so strategies can be
exercised with fixed AgentResponses.
"""

import pytest

from claudeway.consensus import (
    Debate,
    WeightedVote,
    parse_structured_output,
)
from claudeway.swarm import AgentResponse, Swarm, SwarmConfig, Task


class StubSwarm(Swarm):
    """A Swarm that never touches the API — for testing strategies in isolation."""

    def __init__(self, revision_responses=None):  # noqa: D401
        self._revision_responses = revision_responses or []
        self.on_event = None  # set explicitly; __init__ is bypassed

    async def _collect_revision_round(self, prior):  # type: ignore[override]
        if not self._revision_responses:
            raise AssertionError("unexpected revision round requested")
        return self._revision_responses.pop(0)


# --- structured output parsing ---


def test_parse_full_contract():
    p = parse_structured_output(
        "Some analysis...\n<answer>use sqlite</answer>\n"
        "<confidence>0.82</confidence>\n<reasoning>well supported</reasoning>"
    )
    assert p.answer == "use sqlite"
    assert abs(p.confidence - 0.82) < 1e-9
    assert p.reasoning == "well supported"


def test_parse_no_meta_falls_back_gracefully():
    p = parse_structured_output("just a plain answer")
    assert p.confidence == 0.5
    assert p.answer == "just a plain answer"
    assert p.reasoning == ""


def test_parse_clamps_confidence():
    assert parse_structured_output(
        "<answer>x</answer><confidence>5</confidence>"
    ).confidence == 1.0
    assert parse_structured_output(
        "<answer>x</answer><confidence>-1</confidence>"
    ).confidence == 0.0


def test_parse_tolerates_truncated_answer_tag():
    """If the model truncates before </answer>, recover the open-tag content.

    Caught by the LangGraph spike: Haiku at tight max_tokens writes prose,
    opens <answer>, runs out of tokens. Earlier parser fell back to raw
    text and the literal <answer> tag leaked into the answer.
    """
    raw = "First some prose.\n\n<answer>PASS"
    p = parse_structured_output(raw)
    assert p.answer == "PASS"
    assert "<answer>" not in p.answer


def test_parse_strips_orphan_open_tag_from_fallback():
    """No closing tag and no useful content after <answer> → empty, not leaky."""
    p = parse_structured_output("<answer>")
    assert p.answer == ""
    assert "<answer>" not in p.answer


def test_consensus_result_to_dict_handles_dict_form_responses():
    """Rebuilding a ConsensusResult from task.result (dict form) must not crash.

    to_dict() used to access r.agent_name, which only exists on
    AgentResponse objects. The wire form is dicts. Now both work.
    """
    from claudeway.consensus import ConsensusResult

    result = ConsensusResult(
        final_answer="ship",
        method="weighted_vote",
        agent_count=2,
        responses=[
            {"agent": "A", "answer": "ship", "confidence": 0.9},
            {"agent": "B", "answer": "ship", "confidence": 0.85},
        ],
    )
    out = result.to_dict()
    assert out["responses"][0]["agent"] == "A"
    assert out["responses"][1]["confidence"] == 0.85


def test_consensus_result_to_dict_handles_agentresponse_objects():
    """The original AgentResponse-object path still works after the fix."""
    from claudeway.consensus import ConsensusResult

    result = ConsensusResult(
        final_answer="ship",
        method="weighted_vote",
        agent_count=1,
        responses=[AgentResponse(agent_name="A", answer="ship", confidence=0.9)],
    )
    out = result.to_dict()
    assert out["responses"][0]["agent"] == "A"
    assert out["responses"][0]["confidence"] == 0.9


# --- weighted vote ---


@pytest.mark.asyncio
async def test_weighted_vote_picks_highest_confidence():
    responses = [
        AgentResponse(agent_name="A", answer="postgres", confidence=0.4),
        AgentResponse(agent_name="B", answer="sqlite", confidence=0.9),
        AgentResponse(agent_name="C", answer="mongo", confidence=0.5),
    ]
    result = await WeightedVote().resolve(responses, StubSwarm())
    assert result.final_answer == "sqlite"
    assert result.disagreed is True  # three different answers => disagreement


@pytest.mark.asyncio
async def test_weighted_vote_flags_agreement_when_answers_converge():
    responses = [
        AgentResponse(agent_name="A", answer="sqlite", confidence=0.6),
        AgentResponse(agent_name="B", answer="sqlite", confidence=0.7),
    ]
    result = await WeightedVote().resolve(responses, StubSwarm())
    assert result.final_answer == "sqlite"
    assert result.disagreed is False


@pytest.mark.asyncio
async def test_weighted_vote_empty_responses():
    result = await WeightedVote().resolve([], StubSwarm())
    assert result.final_answer == ""
    assert result.agent_count == 0


# --- debate ---


@pytest.mark.asyncio
async def test_debate_early_exits_when_agreement_is_high():
    # If agreement is already high, Debate must NOT request a revision round.
    agreed = [
        AgentResponse(agent_name="A", answer="x", confidence=0.95),
        AgentResponse(agent_name="B", answer="x", confidence=0.93),
    ]
    # StubSwarm raises if a revision is requested, failing the test.
    result = await Debate().resolve(agreed, StubSwarm())
    assert result.rounds == 1
    assert result.disagreed is False


@pytest.mark.asyncio
async def test_debate_revises_when_agents_disagree():
    disagreed = [
        AgentResponse(agent_name="A", answer="x", confidence=0.4),
        AgentResponse(agent_name="B", answer="y", confidence=0.3),
    ]
    revised = [
        AgentResponse(agent_name="A", answer="x revised", confidence=0.92),
        AgentResponse(agent_name="B", answer="x revised", confidence=0.9),
    ]
    result = await Debate().resolve(disagreed, StubSwarm(revision_responses=[revised]))
    assert result.rounds == 2
    assert result.final_answer == "x revised"


# --- agreement score edge cases ---


def test_agreement_single_response_is_one():
    assert WeightedVote._agreement_score([AgentResponse(agent_name="A", answer="x")]) == 1.0


def test_agreement_different_answers_low_score():
    rs = [
        AgentResponse(agent_name="A", answer="x", confidence=0.5),
        AgentResponse(agent_name="B", answer="y", confidence=0.5),
    ]
    assert WeightedVote._agreement_score(rs) < 0.6


# --- failed-agent path (gather with return_exceptions=True) ------------------
#
# The real `_collect_agent_responses` uses asyncio.gather(return_exceptions=True)
# so a single agent raising doesn't abort the round. This is the load-bearing
# failure path — no test in the suite exercised it before. Locked here as a
# prerequisite before adding streaming hooks that touch the same code.


class _GatherSwarm(Swarm):
    """Swarm whose `_query_agent` is faked so we can inject failures.

    Builds real Swarm machinery (so self.agents is populated) but skips the
    Agent client init by overriding _initialize_agents to install sentinel
    agents. _query_agent returns canned responses or raises per a map.
    """

    def __init__(self, agent_names, fail=None):
        # Bypass Swarm.__init__ (which would try to build real Agent clients
        # from AgentConfigs + api_key). We only need self.agents + self.config
        # for the gather path.
        self.config = SwarmConfig(name="T", description="", agents=[])
        self.api_key = None
        self.agents = {name: object() for name in agent_names}
        self.consensus = WeightedVote()
        self.task_history = []
        self.on_event = None  # new in Swarm.__init__; set explicitly here
        self._fail = set(fail or [])
        self._round = 0

    async def _query_agent(self, agent_name, task, round_num):
        if agent_name in self._fail:
            raise RuntimeError(f"{agent_name} exploded")
        return AgentResponse(
            agent_name=agent_name,
            answer=f"{agent_name}-says",
            confidence=0.8,
            round=round_num,
        )


@pytest.mark.asyncio
async def test_failed_agent_is_skipped_not_raised():
    """One agent raising must not abort the round; others still appear."""
    swarm = _GatherSwarm(["A", "B", "C"], fail={"B"})
    responses = await swarm._collect_agent_responses(
        Task(id="t", description="d", input_data={})
    )
    names = sorted(r.agent_name for r in responses)
    assert names == ["A", "C"], f"failed agent B leaked into results: {names}"


@pytest.mark.asyncio
async def test_all_agents_failing_yields_empty_not_raise():
    swarm = _GatherSwarm(["A", "B"], fail={"A", "B"})
    responses = await swarm._collect_agent_responses(
        Task(id="t", description="d", input_data={})
    )
    assert responses == []


# --- on_event streaming hook -------------------------------------------------


@pytest.mark.asyncio
async def test_on_event_fires_per_agent_as_they_land():
    """A successful agent must fire AgentCompleted, with the answer's data."""
    from claudeway.events import AgentCompleted

    events: list = []

    async def collector(evt):
        events.append(evt)

    swarm = _GatherSwarm(["A", "B", "C"])
    swarm.on_event = collector
    await swarm._collect_agent_responses(
        Task(id="t-1", description="d", input_data={})
    )

    # Each successful agent fired once, in agent-config order (gather preserves
    # input order even though they run concurrently).
    assert len(events) == 3
    assert all(isinstance(e, AgentCompleted) for e in events)
    assert [e.agent for e in events] == ["A", "B", "C"]
    assert all(e.task_id == "t-1" and e.round == 1 for e in events)
    # The answer the agent produced is in the event, not just the name.
    assert events[0].answer == "A-says"
    assert events[0].confidence == 0.8


@pytest.mark.asyncio
async def test_on_event_does_not_fire_for_failed_agent():
    """A failed agent must NOT emit an event (its exception propagates to gather)."""
    events: list = []

    async def collector(evt):
        events.append(evt)

    swarm = _GatherSwarm(["A", "B"], fail={"B"})
    swarm.on_event = collector
    await swarm._collect_agent_responses(
        Task(id="t", description="d", input_data={})
    )
    # Only A fired; B's RuntimeError propagated and was skipped post-gather.
    assert [e.agent for e in events] == ["A"]


@pytest.mark.asyncio
async def test_on_event_observer_error_does_not_kill_agent():
    """A buggy observer must never turn a successful agent into a failed one.

    The observer runs in try/except inside the wrapper; if it raises, the
    agent's response still returns to gather normally. This is the invariant
    that keeps streaming from changing consensus outcomes.
    """
    call_count = 0

    async def buggy(evt):
        nonlocal call_count
        call_count += 1
        raise RuntimeError("observer broken")

    swarm = _GatherSwarm(["A", "B"])
    swarm.on_event = buggy
    responses = await swarm._collect_agent_responses(
        Task(id="t", description="d", input_data={})
    )
    # Both agents still produced responses despite the observer exploding.
    assert sorted(r.agent_name for r in responses) == ["A", "B"]
    assert call_count == 2  # observer was actually called (and swallowed)


@pytest.mark.asyncio
async def test_on_event_none_is_noop():
    """Default on_event=None must behave exactly like pre-hook swarm.

    The backward-compat invariant: a Swarm constructed without on_event
    produces the same responses as before the hook existed.
    """
    swarm = _GatherSwarm(["A", "B", "C"])
    # on_event=None by default
    responses = await swarm._collect_agent_responses(
        Task(id="t", description="d", input_data={})
    )
    assert sorted(r.agent_name for r in responses) == ["A", "B", "C"]
    assert swarm.on_event is None


@pytest.mark.asyncio
async def test_on_event_emits_consensus_resolved_after_resolve():
    """process() fires one ConsensusResolved at the end, after the per-agent events."""
    from claudeway.events import ConsensusResolved

    events: list = []

    async def collector(evt):
        events.append(evt)

    # Use the real process() path: _GatherSwarm.process inherits from Swarm,
    # which calls _collect_agent_responses (fires AgentCompleted) then
    # consensus.resolve, then the ConsensusResolved event.
    swarm = _GatherSwarm(["A", "B"])
    swarm.on_event = collector
    await swarm.process(Task(id="t-proc", description="d", input_data={}))

    # 2 per-agent + 1 consensus-resolved, in that order.
    assert len(events) == 3
    assert events[-1].kind == "consensus_resolved"
    assert isinstance(events[-1], ConsensusResolved)
    assert events[-1].task_id == "t-proc"
