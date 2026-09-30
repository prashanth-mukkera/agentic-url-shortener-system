"""
CLI entrypoint.

Examples:
    python -m src.cli --scenario greenfield
    python -m src.cli --scenario brownfield
    python -m src.cli --scenario ambiguous
    python -m src.cli --requirement "Add support for QR codes on short links" --interactive
"""
from __future__ import annotations
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.pipeline import build_and_run  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GENERATED_DIR = os.path.join(REPO_ROOT, "generated")

SCENARIOS = {
    "greenfield": "Build a scalable URL shortener service with APIs, persistence, and analytics.",
    "brownfield": "Enhance the URL shortener service to add basic rate limiting on the "
                  "/api/shorten endpoint to prevent abuse, and capture the referrer header "
                  "in click analytics.",
    "ambiguous": "We need to improve reliability and make the platform more robust and modern "
                 "for our users going forward.",
}


def main():
    parser = argparse.ArgumentParser(description="Agentic Software Engineering System")
    parser.add_argument("--scenario", choices=list(SCENARIOS.keys()), help="Run a predefined scenario")
    parser.add_argument("--requirement", type=str, help="Run a custom requirement instead")
    parser.add_argument("--interactive", action="store_true",
                         help="Prompt for real human approval at gated tasks instead of auto-approving")
    parser.add_argument("--force-fallback", action="store_true",
                         help="Always use the deterministic template fallback for reasoning agents, "
                              "even if GEMINI_API_KEY is set. Use this to demo/test the offline path.")
    args = parser.parse_args()

    if args.force_fallback:
        os.environ["FORCE_TEMPLATE_FALLBACK"] = "1"

    if not args.scenario and not args.requirement:
        parser.error("Pass --scenario {greenfield,brownfield,ambiguous} or --requirement '...'")

    requirement_text = args.requirement or SCENARIOS[args.scenario]

    # Brownfield needs the greenfield project to already exist on disk.
    existing_project_dir = None
    if args.scenario == "brownfield" or (args.requirement and "existing" in args.requirement.lower()):
        candidate = os.path.join(GENERATED_DIR, "url_shortener")
        if os.path.isdir(candidate):
            existing_project_dir = candidate
        else:
            print(f"[cli] No existing project at {candidate} — run --scenario greenfield first.")

    print(f"\n=== Running pipeline for: {requirement_text!r} ===\n")
    result = build_and_run(
        requirement_text,
        workspace_dir=GENERATED_DIR,
        interactive=args.interactive,
        existing_project_dir=existing_project_dir,
    )

    print("\n=== Task Summary ===")
    for t in result.tasks:
        print(f"  [{t.status.value:18}] {t.id:24} attempts={t.attempts} {('- ' + t.error) if t.error else ''}")

    print(f"\nOverall success: {result.success}")
    summary_path = result.context.get("summary_path")
    if summary_path:
        print(f"Final engineering summary: {summary_path}")

    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
