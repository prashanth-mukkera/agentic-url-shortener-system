# Agentic Software Engineering System

A working prototype that takes a raw software requirement and, through a
coordinated multi-agent workflow, produces a reviewable engineering
outcome: an implementation plan, generated/modified code, tests, a
validation run, and a risk/trade-off writeup — under a human approval gate.

Built for the mandatory use case: **"Build a scalable URL shortener service
with APIs, persistence, and analytics."**

---

## 1. Architecture Overview

```
                     ┌─────────────────────────────────────────┐
                     │              Orchestrator                │
                     │  (DAG scheduler, retries, approval gates, │
                     │   error handling & recovery, shared       │
                     │   Context across all agents)              │
                     └──────────────────┬─────────────────────-─┘
                                         │ executes tasks in dependency order
        ┌───────────┬───────────┬───────┴────────┬────────────┬───────────┐
        ▼           ▼           ▼                ▼            ▼           ▼
  Requirement   Task Decomp.  Codebase       Codegen        Test Gen   Validation ─┐
  Understanding              Reasoning     (guarded         Agent      Agent       │
  Agent                      Agent         templates)                             │
                              (brownfield                                          │
                               only)                                 ┌─────────────┘
                                                                      │ on failure (brownfield):
                                                                      ▼ calls back into Codegen's
                                                              repair() then re-validates
        ┌────────────────────────────────────────────────────────────────┐
        ▼                                                                ▼
   Risk & Trade-off Agent  ──────────────────────────────────►  Docs Agent
                                                                (Final Engineering Summary)
```

**Components**

| Component | File | Role |
|---|---|---|
| `Orchestrator` | `src/orchestrator/engine.py` | Builds/validates the task DAG, schedules ready tasks, retries failed ones, enforces approval gates, propagates skips on failed dependencies. |
| `Task` / `Context` | `src/orchestrator/models.py` | `Task` = one DAG node (agent fn, dependencies, retry policy, approval flag). `Context` = mutable state shared across all agents in one run (this is how "cross-step coordination" happens — later agents read what earlier agents wrote). |
| `requirement_agent` | `src/agents/requirement_agent.py` | Classifies greenfield/brownfield/ambiguous, extracts functional/non-functional requirements, or lists clarifying questions + default assumptions for ambiguous input. |
| `decomposition_agent` | `src/agents/decomposition_agent.py` | Produces the human-readable implementation plan (rationale) for the summary doc. |
| `codebase_reasoning_agent` | `src/agents/codebase_reasoning_agent.py` | Brownfield only. Scans the existing generated project for impacted files/routes (stand-in for a code-search/index tool call). |
| `codegen_agent` | `src/agents/codegen_agent.py` | Writes the FastAPI URL shortener (greenfield) or patches it (brownfield). |
| `test_agent` | `src/agents/test_agent.py` | Adds edge-case / regression tests. |
| `validation_agent` | `src/agents/validation_agent.py` | Runs `pytest` against the generated project. On brownfield failure, invokes the codegen repair path and re-validates — the system's concrete error-recovery behavior. |
| `risk_agent` | `src/agents/risk_agent.py` | Produces risks/trade-offs/validation-strategy narrative. |
| `docs_agent` | `src/agents/docs_agent.py` | Assembles everything into the final structured engineering summary (`run_outputs/<scenario>_summary.md`). |
| `pipeline.py` | `src/pipeline.py` | Wires the concrete Task DAG per scenario type (this is the *executable* plan; `decomposition_agent`'s output is the *documented* plan). |

### Execution model & control flow

1. `pipeline.build_and_run()` classifies the requirement (cheaply, for DAG
   shape) and builds a `Task` DAG — greenfield, brownfield, and ambiguous
   requirements get **different shaped pipelines**, not just different
   inputs to the same one (e.g. ambiguous never reaches codegen).
2. `Orchestrator.run()` repeatedly finds tasks whose dependencies are all
   `DONE`, executes them, and marks downstream tasks `SKIPPED` if a
   dependency `FAILED` — this is the dependency/sequencing management.
3. Tasks marked `requires_approval=True` (codegen / patch) pause at an
   approval checkpoint before executing. In the default (non-interactive)
   demo mode the checkpoint auto-approves **but logs it explicitly and
   auditably**; pass `--interactive` to get a real `y/N` prompt. This is
   the "controlled autonomy" requirement — agents still execute
   independently, but every consequential action has a named, logged
   approval point a human can gate.
4. Failed tasks retry up to `max_retries` times (transient-failure
   handling). For the brownfield validation task specifically, a failure
   triggers a *targeted recovery* — the validation agent calls back into
   the codegen agent's `repair_brownfield_patch()` and re-runs the test
   suite — before giving up. This is real, not simulated: the first patch
   genuinely fails; see `run_outputs/brownfield_summary.md` §8 for the
   captured log of it happening.
5. `docs_agent` assembles the final structured summary from everything
   left in `Context` by prior agents.

### Key design decisions

- **Greenfield generation is idempotent regardless of run order.**
  `write_greenfield_project` wipes the target directory before writing —
  so running `brownfield` and then `greenfield` again in the same session
  (e.g. during a live demo) can't leave brownfield-only artifacts (the
  rate limiter patch, `test_rate_limit.py`, `conftest.py`) behind to fail
  against a freshly regenerated, unpatched service.
- **Guarded codegen, not free-form LLM codegen, for the shipped
  deliverable.** `src/llm/client.py` documents this: reasoning/analysis
  agents (requirement understanding, risk narrative) may call the Google
  Gemini API when `GEMINI_API_KEY` is set, with an automatic fallback to
  deterministic templates on any failure (no key, no network, rate limit,
  a hung/unreachable call, etc.) so the prototype **always runs**, with or
  without a key. Code generation for the mandatory deliverable uses
  validated deterministic templates rather than free-form generation — a
  guardrail so generated code can't silently be syntactically broken, and
  so the demo is 100% reproducible for grading. The hook for LLM-driven
  codegen is there (`LLMClient.complete`); it's deliberately not wired into
  the code-writing path for this deliverable.
- **A live LLM call can never hang the pipeline.** The Gemini call runs in
  a daemon thread with a hard 20s wall-clock timeout (`src/llm/client.py`).
  This was found empirically, not assumed: the underlying SDK's own
  timeout parameter didn't reliably stop a stuck call, and an earlier
  version of this guard used a non-daemon thread pool, which meant the
  whole Python process refused to exit even after correctly falling back.
  Both are fixed — a bad key degrades to the template path within ~20
  seconds and the process exits normally.
- **Validation is a hard gate, not a formality.** The brownfield patch
  ships with a real latent bug on purpose (see `codegen_agent.py`
  docstring) so the validation → recovery path is genuinely exercised,
  not narrated.
- **Ambiguous requirements don't get code.** The pipeline shape itself
  changes — it stops after producing clarifying questions, default
  assumptions, and a design recommendation. This reflects a real
  engineering judgment call: writing code against an unclarified
  requirement is a bigger risk than pausing for input.

---

## 2. Deliverable: URL Shortener Service

Generated by running the **greenfield** scenario. Lives at
`generated/url_shortener/` after you run it (see Setup below) — a runnable
FastAPI + SQLAlchemy service:

- `POST /api/shorten` — create a short URL (supports `custom_alias`)
- `GET /{short_code}` — 307 redirect, records a click
- `GET /api/analytics/{short_code}` — click count + recent click history
- `GET /api/health`

The **brownfield** scenario then patches this service in place to add
basic rate limiting on `/api/shorten` (and confirms referrer capture, which
the greenfield build already includes).

---

## 3. Setup Instructions

```bash
cd agentic-sde
pip install -r requirements.txt      # orchestrator deps
# anthropic is optional — only needed if you export ANTHROPIC_API_KEY
# to enable live LLM calls for the reasoning agents; otherwise the
# system runs fully offline on deterministic fallbacks.

# 1) Greenfield — generates the URL shortener service
python3 -m src.cli --scenario greenfield

# 2) Brownfield — patches it (requires step 1 to have run first)
python3 -m src.cli --scenario brownfield

# 3) Ambiguous — design-only, no code
python3 -m src.cli --scenario ambiguous

# Custom requirement:
python3 -m src.cli --requirement "Add QR code generation for short links" --interactive
```

Each run prints a live task-by-task log and writes a structured summary to
`run_outputs/<scenario>_summary.md`.

### Demonstrating live LLM vs. template fallback independently

The reasoning agents (requirement understanding, risk narrative) have two
independent, on-demand modes — useful to show both in an interview without
editing code:

```bash
# 1) LIVE Gemini call — requires a free key from aistudio.google.com
export GEMINI_API_KEY="your-key-here"
python3 -m src.cli --scenario greenfield
# run log will show: "... (analysis via llm-gemini)"

# 2) FORCED template fallback — proves the offline/no-cost path works,
#    even if a valid key is exported in the same shell
python3 -m src.cli --scenario greenfield --force-fallback
# run log will show: "... (analysis via fallback-template (forced))"

# 3) Default with no key set at all — same fallback path, unforced
unset GEMINI_API_KEY
python3 -m src.cli --scenario greenfield
# run log will show: "... (analysis via fallback-template)"
```

Every run's `source` (`llm-gemini` / `fallback-template` / `fallback-template
(forced)`) is printed live and is also visible in `run_outputs/<scenario>_
summary.md` §1 and §6 — that's the fastest way to prove, after the fact,
which path actually ran.

To run the generated service itself:

```bash
cd generated/url_shortener
pip install -r requirements.txt
uvicorn app.main:app --reload
# in another shell:
curl -X POST localhost:8000/api/shorten -H "Content-Type: application/json" \
     -d '{"url": "https://example.com/some/long/path"}'
```

---

## 4. Example Scenarios

Full captured run logs and generated summaries are in `run_outputs/`:

| Scenario | Requirement | Result |
|---|---|---|
| Greenfield | *"Build a scalable URL shortener service with APIs, persistence, and analytics."* | 9 files generated, tests pass on first validation run. `run_outputs/greenfield_summary.md` |
| Brownfield | *"...add basic rate limiting on /api/shorten...capture the referrer header..."* | Impact analysis → patch → **validation fails on attempt 1 → auto-repair → passes on attempt 2**. `run_outputs/brownfield_summary.md` |
| Ambiguous | *"We need to improve reliability and make the platform more robust and modern..."* | Classified as ambiguous → clarifying questions + assumptions produced → **no code generated** → design recommendation only. `run_outputs/ambiguous_summary.md` |

Each summary contains: requirement understanding, the implementation plan
with dependencies, (brownfield) the codebase impact analysis, generated
artifacts, validation result, risks/trade-offs, assumptions/limitations,
and a controlled-autonomy log of every approval/error/recovery event.

---

## 5. Testing Approach

Two independent layers:

1. **Orchestrator tests** (`tests/test_orchestrator.py`) — unit tests for
   the engine itself: dependency ordering, failure → downstream skip
   propagation, retry-recovers-transient-failure, approval-gate
   auto-approval + logging, cycle detection, unknown-dependency detection.
   Run with `pytest tests/ -q`.
2. **Generated-service tests** — written by the codegen/test-gen agents
   into the generated project itself (`generated/url_shortener/tests/`)
   and executed by the `validation_agent` as part of every pipeline run
   (not a separate manual step). Covers the happy path, custom aliases,
   404s, invalid input (422), analytics correctness, and (brownfield) the
   rate limiter.

**Known limitations / trade-offs**

- Codegen is deterministic/template-based for reliability (see §1); it is
  not a general-purpose "generate any requirement into code" system yet —
  extending it to arbitrary requirements would mean wiring the LLM path
  into codegen behind the same validation gate (generate → compile-check →
  test → accept-or-retry), which the architecture already supports but
  this prototype doesn't exercise, to keep the mandatory deliverable
  deterministic and gradeable.
- The brownfield auto-repair path is scoped to the one bug class it's
  designed to catch/fix in this demo, not a general auto-debugger.
- The in-memory rate limiter (brownfield patch) is single-process only —
  noted explicitly in that scenario's risk section.
- Orchestrator executes ready tasks sequentially rather than in a thread/
  process pool; the DAG model supports parallel-eligible tasks (e.g.
  greenfield's `core_logic`/`analytics` sub-steps in the decomposition
  plan) but this prototype keeps execution sequential for simpler,
  deterministic log output during grading.
