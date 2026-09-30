"""
Agent 6 — Validation & Risk Control (execution half).

Runs the generated project's test suite as a subprocess. This is the
system's guardrail: generated code is never considered "done" on the say-so
of the codegen agent alone — it must pass an independent check.

For the brownfield scenario this agent also demonstrates *recovery*: if the
first patch fails validation, it calls back into the codegen agent's repair
function, re-applies, and re-validates — a concrete instance of cross-step
coordination and error handling/recovery, not just a blind per-task retry.
"""
from __future__ import annotations
import os
import subprocess
import sys
from src.agents import codegen_agent


def _run_pytest(project_dir: str) -> tuple[bool, str]:
    env = os.environ.copy()
    env["TESTING"] = "1"
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--tb=short"],
        cwd=project_dir,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    ok = result.returncode == 0
    output = (result.stdout or "") + (result.stderr or "")
    return ok, output


def run(task, context):
    req_type = context.get("requirement_type")

    if req_type == "ambiguous":
        context.log("Ambiguous scenario: no runnable code to validate; validation is a no-op by design.")
        return {"validated": False, "reason": "design-only output"}

    project_dir = context.get("project_dir")
    if not project_dir:
        raise RuntimeError("No project_dir in context; cannot validate.")

    ok, output = _run_pytest(project_dir)
    context.log(f"pytest run #1: {'PASSED' if ok else 'FAILED'}")

    if ok:
        context.set("validation_output", output)
        context.set("validation_repaired", False)
        return {"passed": True, "repaired": False, "attempts": 1}

    if req_type != "brownfield":
        # No defined repair path for greenfield failures in this prototype —
        # surface the failure honestly rather than pretending to fix it.
        context.set("validation_output", output)
        raise RuntimeError(f"Test suite failed and no repair strategy is defined:\n{output[-1500:]}")

    # Brownfield recovery path: repair the known-bug class and retry once.
    context.log("Validation failed — invoking codegen repair path (brownfield auto-recovery).")
    codegen_agent.repair_brownfield_patch(project_dir)
    ok2, output2 = _run_pytest(project_dir)
    context.log(f"pytest run #2 (post-repair): {'PASSED' if ok2 else 'FAILED'}")

    context.set("validation_output", output2)
    context.set("validation_repaired", True)
    context.set("validation_first_failure_excerpt", output[-800:])

    if not ok2:
        raise RuntimeError(f"Test suite still failing after automated repair attempt:\n{output2[-1500:]}")

    return {"passed": True, "repaired": True, "attempts": 2, "first_failure_excerpt": output[-800:]}
