"""
Agent 7 — Validation & Risk Control (analysis half).

Produces the risks/trade-offs/validation-strategy narrative required in the
final engineering summary. Rule-based checklist by requirement type, with an
optional LLM pass to turn it into prose.
"""
from __future__ import annotations
from src.llm.client import LLMClient

CHECKLISTS = {
    "greenfield": [
        "Short-code collisions: mitigated with a bounded regeneration loop; at scale, "
        "move to a counter+base62 or pre-generated key-pool scheme to avoid retries under load.",
        "SQLite is fine for a demo; production needs a real DB (Postgres) with an index on "
        "short_code and a read replica strategy, since redirects are read-heavy.",
        "No auth/rate limiting on /api/shorten in the greenfield build — open to abuse "
        "(spam link creation). Addressed incrementally in the brownfield scenario.",
        "No URL validation beyond format (e.g. no malware/phishing blocklist) — a real "
        "product would integrate a safe-browsing check before persisting.",
        "No expiry/TTL on links — unbounded storage growth over time.",
        "Analytics table grows unbounded; production would need partitioning/rollup jobs.",
    ],
    "brownfield": [
        "In-memory rate limiter resets on process restart and doesn't share state across "
        "multiple app instances — fine for the demo, but needs Redis-backed limiting for "
        "a horizontally scaled deployment.",
        "Rate limiting by client IP is coarse (breaks for users behind shared NAT/proxies); "
        "consider API keys or authenticated quotas for production.",
        "The patch was shipped, caught a real bug in CI/validation, and was auto-repaired — "
        "demonstrates the guardrail working, but any auto-repair action in a real system "
        "should still require human sign-off before merge (see approval gate in the run log).",
    ],
    "ambiguous": [
        "Proceeding on an ambiguous requirement without clarification risks building the "
        "wrong thing; this pipeline deliberately stops at a design recommendation rather "
        "than generating code, and surfaces clarifying questions for the requester.",
        "If clarification is delayed, the documented default assumptions become the de facto "
        "spec — that should be flagged to stakeholders explicitly, not just logged.",
    ],
}

VALIDATION_STRATEGY = {
    "greenfield": "Unit + integration tests via FastAPI TestClient (in-process, no network); "
                  "run automatically in the validation stage before the workflow is marked complete.",
    "brownfield": "Existing regression suite re-run against the patched code, plus a new "
                  "test targeting the specific enhancement; validation failure triggers an "
                  "automated repair-and-retry before falling back to a human-escalation failure.",
    "ambiguous": "N/A — no code artifact was produced; validation here means the clarifying "
                 "questions and assumptions are reviewed by a human before any implementation begins.",
}


def run(task, context):
    req_type = context.get("requirement_type")
    checklist = CHECKLISTS.get(req_type, [])

    llm = LLMClient()
    system = "You are a staff engineer writing a concise risk/trade-off section for an engineering summary."
    prompt = (
        f"Requirement type: {req_type}\n"
        f"Raw requirement: {context.requirement_raw}\n"
        f"Known risk checklist items:\n- " + "\n- ".join(checklist)
    )
    narrative, source = llm.complete(system, prompt, lambda: "\n".join(f"- {c}" for c in checklist))

    context.set("risk_checklist", checklist)
    context.set("risk_narrative", narrative)
    context.set("validation_strategy", VALIDATION_STRATEGY.get(req_type, ""))
    context.log(f"Risk assessment complete ({len(checklist)} items, narrative via {source})")
    return {"num_risks": len(checklist), "source": source}
