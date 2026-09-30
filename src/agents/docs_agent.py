"""
Agent 8 — Final Output.

Assembles everything prior agents produced into the structured engineering
summary required by the assignment: implementation plan & rationale,
generated artifacts, risks/trade-offs/validation approach, and assumptions
& limitations.
"""
from __future__ import annotations
import os
import json


def _plan_md(plan: list[dict]) -> str:
    lines = []
    for step in plan:
        deps = f" (depends on: {', '.join(step['depends_on'])})" if step["depends_on"] else ""
        lines.append(f"- **{step['id']}** — {step['desc']}{deps}")
    return "\n".join(lines)


def run(task, context):
    req_type = context.get("requirement_type")
    plan = context.get("task_plan", [])
    analysis = context.get("requirement_analysis", "")
    impact = context.get("impact_report")
    project_dir = context.get("project_dir")
    files = context.get("generated_files", []) or context.get("brownfield_patch_files", [])
    validation_output = context.get("validation_output", "")
    repaired = context.get("validation_repaired")
    risk_narrative = context.get("risk_narrative", "")
    validation_strategy = context.get("validation_strategy", "")

    md = [f"# Engineering Summary — {req_type.title()} Scenario", ""]
    md.append(f"**Raw requirement:** {context.requirement_raw}")
    md.append("")
    md.append("## 1. Requirement Understanding")
    md.append(analysis)
    md.append("")
    md.append("## 2. Implementation Plan & Rationale")
    md.append(_plan_md(plan))
    md.append("")

    if impact:
        md.append("## 3. Codebase Impact Analysis (brownfield)")
        md.append(f"- Impacted files: `{', '.join(impact['impacted_files'])}`")
        md.append(f"- Existing routes discovered: {impact['existing_routes']}")
        md.append(f"- Change risk: **{impact['risk']}**")
        md.append("")

    md.append("## 4. Generated / Modified Artifacts")
    if files:
        for f in files:
            rel = os.path.relpath(f, project_dir) if project_dir else f
            md.append(f"- `{rel}`")
    else:
        md.append("- (none — design-only output; see §1 for rationale)")
    md.append("")

    md.append("## 5. Validation Approach & Result")
    md.append(validation_strategy)
    if req_type != "ambiguous":
        status = "PASSED" if "failed" not in (validation_output or "").lower() else "FAILED"
        md.append(f"- Test run status: **{status}**" + (" (after automated repair)" if repaired else ""))
        tail = "\n".join((validation_output or "").splitlines()[-8:])
        md.append("```\n" + tail + "\n```")
    md.append("")

    md.append("## 6. Risks, Trade-offs")
    md.append(risk_narrative)
    md.append("")

    md.append("## 7. Assumptions & Limitations")
    if req_type == "greenfield":
        md.append("- SQLite used for persistence (demo-scale); analytics stored per-event, not pre-aggregated.")
        md.append("- No authentication layer; anyone can create/resolve short links.")
        md.append("- Short codes are random 7-char base62, not designed for enumeration-resistance guarantees.")
    elif req_type == "brownfield":
        md.append("- Rate limiter is in-process/in-memory (single-instance only) — a deliberate scope cut for the demo.")
        md.append("- Auto-repair in this prototype is scoped to the one injected bug class shown; it is not a general auto-debugger.")
    else:
        md.append("- No implementation was produced by design; assumptions listed in §1 are provisional pending stakeholder input.")
        md.append("- If proceeding without clarification were required, the system would default to the narrowest interpretation.")
    md.append("")

    md.append("## 8. Controlled Autonomy Log")
    for line in context.events:
        if "APPROVAL" in line or "ERROR" in line or "FAILED" in line or "repair" in line.lower():
            md.append(f"- {line}")

    content = "\n".join(md)

    out_path = os.path.join(context.workspace_dir, "..", "run_outputs", f"{req_type}_summary.md")
    out_path = os.path.normpath(out_path)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        f.write(content)

    context.set("summary_path", out_path)
    context.log(f"Final engineering summary written to {out_path}")
    return {"summary_path": out_path, "length_chars": len(content)}
