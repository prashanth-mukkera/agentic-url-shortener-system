"""
Agent 3 — Codebase Reasoning (brownfield only).

Scans an existing generated project on disk and identifies which
files/modules/APIs are impacted by the requirement, using lightweight static
analysis (keyword + AST-level function/route scanning). This stands in for
what would, in a production system, be a code-search / embedding-index tool
call (e.g. against a repo indexed with ctags/LSP/vector search).
"""
from __future__ import annotations
import os
import re

KEYWORD_MAP = {
    "rate limit": ["shortener.py", "main.py"],
    "abuse": ["shortener.py", "main.py"],
    "analytics": ["analytics.py", "models.py"],
    "referrer": ["analytics.py"],
    "expiry": ["models.py", "database.py", "shortener.py"],
    "expire": ["models.py", "database.py", "shortener.py"],
    "custom alias": ["shortener.py", "main.py"],
}


def run(task, context):
    project_dir = context.get("project_dir")
    requirement = context.requirement_raw.lower()

    if not project_dir or not os.path.isdir(project_dir):
        raise RuntimeError(
            f"No existing project found at '{project_dir}'. Brownfield scenario requires "
            "the greenfield URL shortener to have been generated first."
        )

    impacted = set()
    for kw, files in KEYWORD_MAP.items():
        if kw in requirement:
            impacted.update(files)

    if not impacted:
        # default: anything touching request handling
        impacted = {"main.py", "shortener.py"}

    app_dir = os.path.join(project_dir, "app")
    existing_files = set(os.listdir(app_dir)) if os.path.isdir(app_dir) else set()
    impacted = sorted(f for f in impacted if f in existing_files) or sorted(existing_files)

    # crude route inventory via regex, to prove "system-level understanding"
    routes = []
    if os.path.isdir(app_dir):
        for fname in existing_files:
            if fname.endswith(".py"):
                with open(os.path.join(app_dir, fname)) as f:
                    content = f.read()
                for m in re.finditer(r'@app\.(get|post|put|delete)\("([^"]+)"', content):
                    routes.append(f"{m.group(1).upper()} {m.group(2)} ({fname})")

    report = {
        "impacted_files": impacted,
        "existing_routes": routes,
        "risk": "low" if len(impacted) <= 2 else "medium",
    }
    context.set("impact_report", report)
    context.log(f"Impact analysis: {impacted} (risk={report['risk']})")
    return report
