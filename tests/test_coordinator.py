"""
Coordinator tests — decomposition JSON parsing + dependency-respecting execution.

No API calls: the coordinator agent is stubbed, so we test the orchestration
logic (JSON extraction, specialist assignment, parallel/serial scheduling,
dependency context injection) in isolation.
"""

import pytest

from claudeway.coordinator import Coordinator, SubTask, _extract_json_object

# --- JSON plan extraction ---


def test_extract_plain_json():
    assert _extract_json_object('{"a": 1}')['a'] == 1


def test_extract_fenced_json():
    text = 'here\n```json\n{"sub_tasks": []}\n```\nend'
    assert _extract_json_object(text)["sub_tasks"] == []


def test_extract_json_embedded_in_prose():
    text = 'I think {"sub_tasks": [{"id": "1"}]} done'
    parsed = _extract_json_object(text)
    assert parsed is not None
    assert parsed["sub_tasks"][0]["id"] == "1"


def test_extract_returns_none_on_garbage():
    assert _extract_json_object("no json here at all") is None


# --- fake agent + coordinator for scheduling tests ---


class FakeAgent:
    def __init__(self, name, role=None):
        self.name = name
        # Give each fake a role so the real _pick_specialist can match it.
        class _Cfg:
            pass
        self.config = _Cfg()
        self.config.role = role or name

    async def think(self, prompt):
        # Echo which agent ran + whether dependency context was injected.
        marker = "[ctx]" if "Prior sub-task" in prompt else ""
        return f"{self.name}-ran{marker}"


class FakeCoordinator(Coordinator):
    def __init__(self):
        pass  # bypass Agent/client init
    # Deliberately do NOT override _pick_specialist — exercise the real one.


@pytest.fixture
def coordinator():
    c = FakeCoordinator()
    # Specialists named "A" and "B"; roles match names so _pick_specialist
    # can resolve by name, role-substring, or fallback.
    c.sub_agents = {"A": FakeAgent("A", role="A"), "B": FakeAgent("B", role="B")}
    return c


# --- specialist assignment ---


@pytest.mark.asyncio
async def test_assign_by_specialist_role(coordinator):
    subs = [
        SubTask(id="1", parent_task="t", description="d1", specialist_role="A"),
        SubTask(id="2", parent_task="t", description="d2", specialist_role="B"),
    ]
    await coordinator._assign_sub_tasks(subs)
    assert subs[0].assigned_to == "A"
    assert subs[1].assigned_to == "B"


@pytest.mark.asyncio
async def test_assignment_falls_back_when_no_specialist_match(coordinator):
    sub = SubTask(id="1", parent_task="t", description="d", specialist_role="zzz")
    await coordinator._assign_sub_tasks([sub])
    # Falls back to the first available specialist.
    assert sub.assigned_to == "A"


# --- dependency-respecting execution ---


@pytest.mark.asyncio
async def test_independent_subtasks_all_run(coordinator):
    subs = [
        SubTask(id="1", parent_task="t", description="d1", specialist_role="A"),
        SubTask(id="2", parent_task="t", description="d2", specialist_role="B"),
    ]
    await coordinator._assign_sub_tasks(subs)
    results = await coordinator._execute_sub_tasks(subs)
    assert results["1"] == "A-ran"
    assert results["2"] == "B-ran"
    assert all(s.status == "completed" for s in subs)


@pytest.mark.asyncio
async def test_dependent_subtask_gets_prior_context(coordinator):
    """A sub-task depending on another must receive the prior result as context."""
    subs = [
        SubTask(id="1", parent_task="t", description="d1", specialist_role="A"),
        SubTask(id="2", parent_task="t", description="d2", specialist_role="B",
                dependencies=["1"]),
    ]
    await coordinator._assign_sub_tasks(subs)
    results = await coordinator._execute_sub_tasks(subs)
    # Sub 2 should have run and its result should reflect injected context.
    assert "[ctx]" in results["2"]


@pytest.mark.asyncio
async def test_unresolvable_dependency_does_not_hang(coordinator):
    """A dependency on a non-existent id must not deadlock the scheduler."""
    subs = [
        SubTask(id="1", parent_task="t", description="d", specialist_role="A",
                dependencies=["ghost"]),
    ]
    await coordinator._assign_sub_tasks(subs)
    results = await coordinator._execute_sub_tasks(subs)
    # Scheduler marks it failed rather than hanging.
    assert "error" in results["1"]
    assert subs[0].status == "failed"


# --- graceful degradation ---


def test_parse_plan_falls_back_when_unparseable():
    """A bad coordinator response degrades to a single whole-task sub-task."""
    subs = Coordinator._parse_plan("complete garbage", parent_id="t")
    assert len(subs) == 1
    assert subs[0].parent_task == "t"


def test_parse_plan_handles_empty_subtasks_list():
    subs = Coordinator._parse_plan('{"sub_tasks": []}', parent_id="t")
    assert len(subs) == 1  # degrades to single whole-task
