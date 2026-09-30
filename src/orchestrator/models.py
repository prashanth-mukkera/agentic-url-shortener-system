"""
Core data models for the agentic orchestration engine.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional, Any
import time


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    DONE = "DONE"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


@dataclass
class Task:
    """A single unit of work in the workflow DAG."""
    id: str
    name: str
    agent: Callable[["Task", "Context"], dict]
    depends_on: list[str] = field(default_factory=list)
    requires_approval: bool = False
    max_retries: int = 1
    critical: bool = True  # if True, failure halts downstream dependents

    status: TaskStatus = TaskStatus.PENDING
    attempts: int = 0
    result: Optional[dict] = None
    error: Optional[str] = None
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    log: list[str] = field(default_factory=list)

    def duration(self) -> float:
        if self.started_at and self.finished_at:
            return round(self.finished_at - self.started_at, 3)
        return 0.0


@dataclass
class Context:
    """
    Shared mutable state passed between agents/tasks during a workflow run.
    Agents read prior outputs from here and write their own outputs back.
    """
    requirement_raw: str
    workspace_dir: str
    interactive: bool = False
    data: dict[str, Any] = field(default_factory=dict)
    events: list[str] = field(default_factory=list)

    def log(self, msg: str):
        ts = time.strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        self.events.append(line)
        print(line)

    def set(self, key: str, value: Any):
        self.data[key] = value

    def get(self, key: str, default=None):
        return self.data.get(key, default)


@dataclass
class WorkflowResult:
    tasks: list[Task]
    context: Context
    success: bool
    artifacts: dict[str, str] = field(default_factory=dict)  # name -> path
