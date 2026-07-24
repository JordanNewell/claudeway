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
from claudeway.swarm import AgentResponse, Swarm


class StubSwarm(Swarm):
    """A Swarm that never touches the API — for testing strategies in isolation."""

    def __init__(self, revision_responses=None):  # noqa: D401
        self._revision_responses = revision_responses or []

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
