"""
Unit tests for the orchestration engine (not the generated URL shortener —
see generated/url_shortener/tests for that). Run with:
    pytest tests/test_orchestrator.py -q
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from src.orchestrator.models import Task, Context, TaskStatus
from src.orchestrator.engine import Orchestrator


def make_ctx():
    return Context(requirement_raw="test", workspace_dir="/tmp/agentic-sde-test")


def test_linear_dependency_order():
    calls = []

    def a(t, c):
        calls.append("a")

    def b(t, c):
        calls.append("b")

    tasks = [
        Task(id="a", name="A", agent=a, depends_on=[]),
        Task(id="b", name="B", agent=b, depends_on=["a"]),
    ]
    result = Orchestrator(tasks, make_ctx()).run()
    assert calls == ["a", "b"]
    assert result.success


def test_failed_critical_task_skips_downstream():
    def fails(t, c):
        raise RuntimeError("boom")

    def never_runs(t, c):
        raise AssertionError("should not run")

    tasks = [
        Task(id="a", name="A", agent=fails, depends_on=[], max_retries=0, critical=True),
        Task(id="b", name="B", agent=never_runs, depends_on=["a"]),
    ]
    result = Orchestrator(tasks, make_ctx()).run()
    a = next(t for t in result.tasks if t.id == "a")
    b = next(t for t in result.tasks if t.id == "b")
    assert a.status == TaskStatus.FAILED
    assert b.status == TaskStatus.SKIPPED
    assert not result.success


def test_retry_recovers_transient_failure():
    attempts = {"n": 0}

    def flaky(t, c):
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise RuntimeError("transient")
        return {"ok": True}

    tasks = [Task(id="a", name="A", agent=flaky, depends_on=[], max_retries=2)]
    result = Orchestrator(tasks, make_ctx()).run()
    assert result.success
    assert attempts["n"] == 2


def test_approval_gate_auto_approves_in_noninteractive_mode():
    ran = {"v": False}

    def gated(t, c):
        ran["v"] = True

    ctx = make_ctx()
    ctx.interactive = False
    tasks = [Task(id="a", name="A", agent=gated, depends_on=[], requires_approval=True)]
    result = Orchestrator(tasks, ctx).run()
    assert ran["v"] is True
    assert any("APPROVAL GRANTED" in e for e in result.context.events)


def test_cycle_detection_raises():
    tasks = [
        Task(id="a", name="A", agent=lambda t, c: None, depends_on=["b"]),
        Task(id="b", name="B", agent=lambda t, c: None, depends_on=["a"]),
    ]
    with pytest.raises(ValueError):
        Orchestrator(tasks, make_ctx())


def test_unknown_dependency_raises():
    tasks = [Task(id="a", name="A", agent=lambda t, c: None, depends_on=["ghost"])]
    with pytest.raises(ValueError):
        Orchestrator(tasks, make_ctx())
