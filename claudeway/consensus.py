"""
Claudeway Consensus - How multiple agents reach agreement.

The core differentiator. Frameworks like LangGraph make you wire coordination
by hand; CrewAI's coordination is shallow. Here, consensus is a first-class,
pluggable primitive: give the swarm agents and a task, get back an answer the
agents actually agreed on — with disagreement surfaced, not hidden.

Two strategies ship:
  - WeightedVote (default): aggregate per-agent responses weighted by the
    confidence each agent reports. Cheap, one round.
  - Debate: agents see each other's answers and revise once. More calls,
    higher-quality agreement on hard questions.

Implement ConsensusStrategy to add your own (e.g. tournament, human-in-loop).
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .swarm import AgentResponse, Swarm


# --- Output contract parsing -------------------------------------------------
#
# Agents are asked (via the swarm prompt) to end their response with a
# structured block. We parse it out; if absent, confidence defaults to 0.5
# so the system degrades gracefully rather than breaking.

_CONFIDENCE_RE = re.compile(
    r"<confidence>\s*(-?[0-9]*\.?[0-9]+)\s*</confidence>", re.IGNORECASE
)
_REASONING_RE = re.compile(
    r"<reasoning>\s*(.*?)\s*</reasoning>", re.IGNORECASE | re.DOTALL
)
_ANSWER_RE = re.compile(
    r"<answer>\s*(.*?)\s*</answer>", re.IGNORECASE | re.DOTALL
)
# Tolerant variant: matches an <answer> opened but never closed (model ran
# out of tokens before the close tag). Falls back to "everything after the
# opening tag." Caught by the LangGraph spike on small-model + tight
# max_tokens paths.
_ANSWER_OPEN_RE = re.compile(
    r"<answer>\s*(.*)$", re.IGNORECASE | re.DOTALL
)


@dataclass
class ParsedResponse:
    """An agent response split into the answer and the structured meta."""

    answer: str
    confidence: float = 0.5
    reasoning: str = ""


def parse_structured_output(raw: str) -> ParsedResponse:
    """
    Parse the structured tail of an agent response.

    Agents are prompted to emit:
        <answer>...the substantive answer...</answer>
        <confidence>0.0-1.0</confidence>
        <reasoning>why</reasoning>

    Tolerant of three failure modes:
      - No tags at all: whole raw text becomes the answer.
      - Open-but-not-closed <answer> (small models truncating at
        max_tokens): everything after the opening tag is the answer.
      - Missing confidence/reasoning: defaults kick in (0.5 / "").
    """
    answer_match = _ANSWER_RE.search(raw)
    if answer_match:
        answer = answer_match.group(1).strip()
    else:
        open_match = _ANSWER_OPEN_RE.search(raw)
        if open_match:
            # Truncated response: take everything after <answer> as the
            # answer, but strip any trailing meta blocks that did fit.
            answer = _strip_meta_blocks(open_match.group(1)).strip()
        else:
            # No tags at all — keep raw minus any stray meta blocks.
            answer = _strip_meta_blocks(raw).strip()

    conf_match = _CONFIDENCE_RE.search(raw)
    confidence = float(conf_match.group(1)) if conf_match else 0.5
    confidence = max(0.0, min(1.0, confidence))  # clamp

    reasoning_match = _REASONING_RE.search(raw)
    reasoning = reasoning_match.group(1).strip() if reasoning_match else ""

    return ParsedResponse(answer=answer, confidence=confidence, reasoning=reasoning)


def _strip_meta_blocks(text: str) -> str:
    """Remove our structured meta tags so the answer reads cleanly."""
    cleaned = text
    for pattern in (_ANSWER_RE, _CONFIDENCE_RE, _REASONING_RE):
        cleaned = pattern.sub("", cleaned)
    # Also strip orphan opening tags from truncated responses.
    cleaned = _ANSWER_OPEN_RE.sub("", cleaned)
    return cleaned


def _response_to_dict(r: Any) -> dict:
    """Normalize an AgentResponse OR its dict form to the wire shape.

    task.result is always the dict form (it round-tripped through
    to_dict). Rebuilding a ConsensusResult from that dict used to crash
    to_dict() on the second pass because r.agent_name doesn't exist on
    dicts. Handle both.
    """
    if isinstance(r, dict):
        return {
            "agent": r.get("agent") or r.get("agent_name") or "",
            "confidence": r.get("confidence", 0.5),
            "answer": r.get("answer", ""),
        }
    return {
        "agent": r.agent_name,
        "confidence": r.confidence,
        "answer": r.answer,
    }


# --- Consensus result --------------------------------------------------------


@dataclass
class ConsensusResult:
    """The outcome of a consensus round."""

    final_answer: str
    method: str
    agent_count: int
    responses: list[AgentResponse]
    agreement: float = 0.0  # 0..1, how aligned agents were (1 = full)
    rounds: int = 1
    disagreed: bool = False

    def to_dict(self) -> dict:
        return {
            "final_answer": self.final_answer,
            "method": self.method,
            "agent_count": self.agent_count,
            "agreement": round(self.agreement, 3),
            "rounds": self.rounds,
            "disagreed": self.disagreed,
            "responses": [_response_to_dict(r) for r in self.responses],
        }


# --- Strategy interface ------------------------------------------------------


class ConsensusStrategy(ABC):
    """
    How a swarm turns many agent responses into one answer.

    Implementations receive the responses collected for the current round and
    return a ConsensusResult. They may request additional rounds (Debate) by
    calling back into the swarm for revised responses.
    """

    name: str = "abstract"

    @abstractmethod
    async def resolve(
        self, responses: list[AgentResponse], swarm: Swarm
    ) -> ConsensusResult:
        """Turn responses into a ConsensusResult."""
        ...

    # Helper shared by strategies: a quick agreement score in [0, 1].
    #
    # TODO(semantic-agreement): this only catches surface-form matches via
    # _normalize_answer. Three agents writing different prose that
    # substantively agrees get scored ~33%. Real fix is a semantic-similarity
    # scorer (embeddings, or an LLM judge) — bigger change, tracked in
    # BENCHMARK-RESEARCH.md §6 as part of the benchmark harness work.
    @staticmethod
    def _agreement_score(responses: list[AgentResponse]) -> float:
        """
        Share of total confidence backing the plurality answer.

        Groups responses by their (normalized) answer text and asks: of all
        the confidence mass in the room, how much points at the most popular
        answer? 1.0 = everyone converged on one answer; ~0.5 = split.
        """
        if len(responses) <= 1:
            return 1.0
        weights: dict[str, float] = {}
        total = 0.0
        for r in responses:
            key = _normalize_answer(r.answer)
            weights[key] = weights.get(key, 0.0) + max(r.confidence, 0.0)
            total += max(r.confidence, 0.0)
        if total <= 0:
            return 0.0
        return max(weights.values()) / total


# --- Weighted vote -----------------------------------------------------------


class WeightedVote(ConsensusStrategy):
    """
    Pick the highest-confidence answer, surfacing disagreement.

    One round, N calls. Default for cost reasons.
    """

    name = "weighted_vote"

    async def resolve(
        self, responses: list[AgentResponse], swarm: Swarm
    ) -> ConsensusResult:
        if not responses:
            return ConsensusResult(
                final_answer="",
                method=self.name,
                agent_count=0,
                responses=[],
                agreement=0.0,
                disagreed=False,
            )

        agreement = self._agreement_score(responses)
        winner = max(responses, key=lambda r: r.confidence)
        disagreed = agreement < 0.6 or winner.confidence < 0.6

        return ConsensusResult(
            final_answer=winner.answer,
            method=self.name,
            agent_count=len(responses),
            responses=responses,
            agreement=agreement,
            rounds=1,
            disagreed=disagreed,
        )


# --- Debate ------------------------------------------------------------------


class Debate(ConsensusStrategy):
    """
    One revision round: agents see peers' answers and revise.

    2N calls total. Use for genuinely hard questions where WeightedVote
    disagrees. The final answer is the highest-confidence revised response.
    """

    name = "debate"
    rounds: int = 2

    def __init__(self, agreement_threshold: float = 0.8) -> None:
        """
        agreement_threshold: if the first round's agreement score is at or
        above this, the debate is considered settled and the costly revision
        round is skipped.
        """
        self.agreement_threshold = agreement_threshold

    async def resolve(
        self, responses: list[AgentResponse], swarm: Swarm
    ) -> ConsensusResult:
        if not responses:
            return ConsensusResult(
                final_answer="",
                method=self.name,
                agent_count=0,
                responses=[],
            )

        first_agreement = self._agreement_score(responses)

        # Early exit: if agents already agree, skip the costly second round.
        if first_agreement >= self.agreement_threshold:
            winner = max(responses, key=lambda r: r.confidence)
            return ConsensusResult(
                final_answer=winner.answer,
                method=self.name,
                agent_count=len(responses),
                responses=responses,
                agreement=first_agreement,
                rounds=1,
                disagreed=False,
            )

        # Round 2: each agent sees the others' answers and revises.
        revised = await swarm._collect_revision_round(responses)
        agreement = self._agreement_score(revised)
        winner = max(revised, key=lambda r: r.confidence)

        return ConsensusResult(
            final_answer=winner.answer,
            method=self.name,
            agent_count=len(revised),
            responses=revised,
            agreement=agreement,
            rounds=2,
            disagreed=agreement < self.agreement_threshold,
        )


# --- Helpers -----------------------------------------------------------------


def _normalize_answer(text: str) -> str:
    """
    Normalize an answer string for agreement comparison.

    Lowercases, collapses whitespace, strips trailing punctuation. Answers
    that differ only in surface form count as the same.
    """
    if not text:
        return ""
    return re.sub(r"\s+", " ", text.strip().lower().rstrip(".!?"))
