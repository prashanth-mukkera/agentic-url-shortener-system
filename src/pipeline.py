"""
Builds the concrete Task DAG for a given requirement and runs it through the
Orchestrator. This is where "which agents, in what order, with which
dependencies and gates" is decided — the decomposition_agent's output is the
*documented rationale*; this is the *executable* plan.
"""
from __future__ import annotations
import os
from src.orchestrator.models import Task, Context
from src.orchestrator.engine import Orchestrator
from src.agents import (
    requirement_agent,
    decomposition_agent,
    codebase_reasoning_agent,
    codegen_agent,
    test_agent,
    validation_agent,
    risk_agent,
    docs_agent,
)


def build_and_run(requirement_text: str, workspace_dir: str, interactive: bool = False,
                   existing_project_dir: str | None = None):
    context = Context(requirement_raw=requirement_text, workspace_dir=workspace_dir, interactive=interactive)
    if existing_project_dir:
        context.set("project_dir", existing_project_dir)

    os.makedirs(workspace_dir, exist_ok=True)

    tasks = [
        Task(id="requirement_understanding", name="Requirement Understanding",
             agent=requirement_agent.run, depends_on=[]),
        Task(id="task_decomposition", name="Task Decomposition",
             agent=decomposition_agent.run, depends_on=["requirement_understanding"]),
    ]

    # Classification happens inside requirement_understanding, but we need to
    # branch the *pipeline shape* before running it. We do a cheap pre-classify
    # pass here (same heuristic) purely for DAG construction; the authoritative
    # classification used everywhere else still comes from the agent's own run.
    pre_type = requirement_agent._classify(requirement_text)

    if pre_type == "ambiguous":
        tasks += [
            Task(id="risk_assessment", name="Risk & Trade-off Assessment",
                 agent=risk_agent.run, depends_on=["task_decomposition"]),
            Task(id="docs_generation", name="Final Engineering Summary",
                 agent=docs_agent.run, depends_on=["risk_assessment"]),
        ]
    elif pre_type == "brownfield":
        tasks += [
            Task(id="codebase_reasoning", name="Codebase Impact Analysis",
                 agent=codebase_reasoning_agent.run, depends_on=["task_decomposition"], critical=True),
            Task(id="codegen", name="Implement Patch",
                 agent=codegen_agent.run_brownfield, depends_on=["codebase_reasoning"],
                 requires_approval=True, max_retries=0),
            Task(id="test_generation", name="Regression Test Generation",
                 agent=test_agent.run, depends_on=["codegen"]),
            Task(id="validation", name="Validate (with auto-repair on failure)",
                 agent=validation_agent.run, depends_on=["test_generation"], max_retries=0),
            Task(id="risk_assessment", name="Risk & Trade-off Assessment",
                 agent=risk_agent.run, depends_on=["validation"]),
            Task(id="docs_generation", name="Final Engineering Summary",
                 agent=docs_agent.run, depends_on=["risk_assessment"]),
        ]
    else:  # greenfield
        tasks += [
            Task(id="codegen", name="Generate Service Implementation",
                 agent=codegen_agent.run_greenfield, depends_on=["task_decomposition"],
                 requires_approval=True, max_retries=0),
            Task(id="test_generation", name="Test Generation",
                 agent=test_agent.run, depends_on=["codegen"]),
            Task(id="validation", name="Validate",
                 agent=validation_agent.run, depends_on=["test_generation"], max_retries=0),
            Task(id="risk_assessment", name="Risk & Trade-off Assessment",
                 agent=risk_agent.run, depends_on=["validation"]),
            Task(id="docs_generation", name="Final Engineering Summary",
                 agent=docs_agent.run, depends_on=["risk_assessment"]),
        ]

    orchestrator = Orchestrator(tasks, context)
    result = orchestrator.run()
    return result
