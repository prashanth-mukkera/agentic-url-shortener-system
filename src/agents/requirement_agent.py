"""
Agent 1 — Requirement Understanding.

Interprets the raw requirement text, classifies it (greenfield / brownfield /
ambiguous), extracts functional & non-functional requirements, and — for
ambiguous input — produces clarifying questions plus the reasonable default
assumptions the pipeline will proceed under (so the system never simply stalls
on ambiguity; it documents its interpretation instead, which is then visible
to a human reviewer at the approval gate).
"""
from __future__ import annotations
from src.llm.client import LLMClient

BROWNFIELD_HINTS = ["enhance", "add", "extend", "fix", "refactor", "improve", "existing",
                     "migrate", "optimi", "upgrade", "bug"]
VAGUE_HINTS = ["improve", "better", "modernize", "revamp", "enhance the experience",
               "make it faster", "more robust", "user-friendly"]


def _classify(text: str) -> str:
    t = text.lower()
    concrete_signals = ["api", "endpoint", "schema", "database", "service", "persistence",
                         "shorten", "analytics", "scalable"]
    has_concrete = sum(s in t for s in concrete_signals)
    has_brownfield = any(h in t for h in BROWNFIELD_HINTS)
    vague_score = sum(h in t for h in VAGUE_HINTS)

    if vague_score >= 1 and has_concrete == 0:
        return "ambiguous"
    if has_brownfield and "build a" not in t and "build" not in t.split(",")[0]:
        return "brownfield"
    return "greenfield"


def _fallback_analysis(text: str, req_type: str) -> str:
    lines = [f"Requirement type: {req_type}", ""]
    if req_type == "ambiguous":
        lines += [
            "Ambiguities identified:",
            "- Scope/platform not specified (web, mobile, API-only?)",
            "- No measurable success criteria given for 'improve/better'",
            "- No constraints given (timeline, budget, existing system boundaries)",
            "",
            "Clarifying questions a human PM/engineer would ask:",
            "- Which specific pain point should be addressed first?",
            "- Is there an existing system being modified, or is this net-new?",
            "- What does success look like quantitatively?",
            "",
            "Default assumptions to proceed under (flagged for reviewer approval):",
            "- Treat as a discovery/design task, not a full implementation task.",
            "- Assume the request concerns a user-facing web flow unless corrected.",
        ]
    else:
        lines += [
            "Functional requirements:",
            "- Accept a long URL and return a short, unique alias",
            "- Redirect short alias -> original URL",
            "- Persist mappings durably",
            "- Track and expose usage analytics (click counts, timestamps)",
            "",
            "Non-functional requirements:",
            "- Scalable to high read (redirect) volume",
            "- Low latency redirects",
            "- Collision-free short code generation",
        ]
    return "\n".join(lines)


def run(task, context):
    llm = LLMClient()
    req_type = _classify(context.requirement_raw)

    system = ("You are a senior requirements analyst. Given a raw software requirement, "
               "classify it as greenfield, brownfield, or ambiguous, extract functional and "
               "non-functional requirements, and list concrete ambiguities if any. Be concise.")
    prompt = f"Requirement:\n{context.requirement_raw}\n\nProvisional classification: {req_type}"

    analysis_text, source = llm.complete(system, prompt, lambda: _fallback_analysis(context.requirement_raw, req_type))

    context.set("requirement_type", req_type)
    context.set("requirement_analysis", analysis_text)
    context.set("requirement_analysis_source", source)
    context.log(f"Requirement classified as '{req_type}' (analysis via {source})")

    return {
        "requirement_type": req_type,
        "analysis_source": source,
        "analysis_preview": analysis_text[:200],
    }
