"""
Agent 2 — Task Decomposition.

Breaks the normalized requirement into a structured plan (name, description,
dependency on other planned steps). This plan is descriptive metadata used in
the final engineering summary — the *actual* execution DAG is defined in
pipeline.py using the orchestrator's Task objects, but this agent's output is
what a human reviewer reads to understand the rationale before approving.
"""
from __future__ import annotations


def _plan_for(req_type: str) -> list[dict]:
    if req_type == "ambiguous":
        return [
            {"id": "clarify", "desc": "Surface ambiguities & propose default assumptions", "depends_on": []},
            {"id": "design_only", "desc": "Produce a design recommendation (no code) under stated assumptions",
             "depends_on": ["clarify"]},
            {"id": "risk", "desc": "Flag risk of proceeding without stakeholder confirmation", "depends_on": ["design_only"]},
        ]
    if req_type == "brownfield":
        return [
            {"id": "impact_analysis", "desc": "Identify impacted modules/APIs in the existing codebase", "depends_on": []},
            {"id": "patch_design", "desc": "Design the minimal change set", "depends_on": ["impact_analysis"]},
            {"id": "implement_patch", "desc": "Apply code changes", "depends_on": ["patch_design"]},
            {"id": "regression_tests", "desc": "Add/extend tests covering the change and existing behavior", "depends_on": ["implement_patch"]},
            {"id": "validate", "desc": "Run test suite; auto-repair on first failure", "depends_on": ["regression_tests"]},
        ]
    # greenfield
    return [
        {"id": "api_contract", "desc": "Define REST API contract (endpoints, request/response schemas)", "depends_on": []},
        {"id": "data_model", "desc": "Define persistence schema", "depends_on": ["api_contract"]},
        {"id": "core_logic", "desc": "Implement short-code generation & redirect logic", "depends_on": ["data_model"]},
        {"id": "analytics", "desc": "Implement click/analytics tracking", "depends_on": ["data_model"]},
        {"id": "tests", "desc": "Generate unit + integration tests", "depends_on": ["core_logic", "analytics"]},
        {"id": "validate", "desc": "Run test suite against generated service", "depends_on": ["tests"]},
    ]


def run(task, context):
    req_type = context.get("requirement_type")
    plan = _plan_for(req_type)
    context.set("task_plan", plan)
    context.log(f"Decomposed into {len(plan)} sub-tasks for type='{req_type}'")
    return {"num_subtasks": len(plan), "plan": plan}
