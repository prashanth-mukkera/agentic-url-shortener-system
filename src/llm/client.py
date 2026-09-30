"""
Thin wrapper around the Google Gemini API used for the *reasoning* agents
(requirement understanding, ambiguity detection, risk narration, docs).

Design decision (documented in README "Guardrails" section):
  Reasoning/analysis steps may call the LLM when GEMINI_API_KEY (or
  GOOGLE_API_KEY) is set. Code generation for the mandatory deliverable does
  NOT depend on the LLM — it uses validated, deterministic templates so the
  prototype is reproducible and runnable in any environment (including one
  with no API key), and so generated code can't silently fail to compile.
  This is a controlled-autonomy guardrail: free-form generation is used
  where mistakes are cheap to review (prose/analysis), and constrained
  generation is used where mistakes are expensive (shipped code).

Two independent, demonstrable modes (see README §"Demonstrating LLM vs
fallback" for the exact commands):
  1. Live Gemini call   — GEMINI_API_KEY set, FORCE_TEMPLATE_FALLBACK unset.
  2. Forced fallback    — FORCE_TEMPLATE_FALLBACK=1 (or `--force-fallback`
                           on the CLI), regardless of whether a key is set.
                           Lets you prove the offline/no-cost path works
                           even in an environment that *does* have a key.
Any real-world failure (no key, bad key, network error, rate limit, import
error) also silently lands on the fallback — that's the guardrail, not a
third mode; `source` in the returned tuple tells you which path actually ran.
"""
from __future__ import annotations
import os
import threading

LLM_TIMEOUT_SECONDS = 20


class LLMClient:
    def __init__(self, force_fallback: bool | None = None):
        """
        force_fallback:
          - True  -> always use the template fallback, even if a valid key
                     is present. Use this to test/demo the fallback path in
                     isolation.
          - False -> attempt the live Gemini call unconditionally.
          - None (default) -> read FORCE_TEMPLATE_FALLBACK from the
                     environment ("1"/"true"/"yes" forces fallback);
                     otherwise normal behavior (live call if a key is
                     present, fallback if not).
        """
        if force_fallback is None:
            force_fallback = os.environ.get("FORCE_TEMPLATE_FALLBACK", "").strip().lower() in ("1", "true", "yes")
        self.force_fallback = force_fallback

        self.api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        self.enabled = False
        self._model = None

        if self.api_key and not self.force_fallback:
            try:
                import google.generativeai as genai  # type: ignore
                genai.configure(api_key=self.api_key)
                self._model = genai.GenerativeModel("gemini-1.5-flash")
                self.enabled = True
            except ImportError:
                self.enabled = False

    def complete(self, system: str, prompt: str, fallback):
        """
        Try a real LLM call; on any failure (no key, no package, network,
        rate limit, etc.) — or when forced — fall back to a deterministic
        function so the pipeline never breaks the demo.
        """
        if self.force_fallback:
            return fallback(), "fallback-template (forced)"

        if self.enabled:
            # The underlying gRPC transport doesn't reliably honor its own
            # request_options timeout on every failure path (observed: a
            # bad/unreachable key can retry for well over a minute). Enforce
            # a hard wall-clock timeout ourselves via a *daemon* thread —
            # daemon=True matters: a non-daemon thread pool leaves the whole
            # Python process unable to exit even after we've given up and
            # fallen back, because the interpreter waits for non-daemon
            # threads to finish at shutdown. A daemon thread lets the
            # process exit normally while the stuck call is abandoned.
            box: dict = {}

            def _worker():
                try:
                    box["text"] = self._call_gemini(system, prompt)
                except Exception as e:  # noqa: BLE001
                    box["error"] = e

            t = threading.Thread(target=_worker, daemon=True)
            t.start()
            t.join(timeout=LLM_TIMEOUT_SECONDS)

            if not t.is_alive():
                text = box.get("text")
                if text and text.strip():
                    return text, "llm-gemini"
            # else: still running past the timeout, or it raised — abandon
            # it and fall back; the daemon thread will die with the process.
        return fallback(), "fallback-template"

    def _call_gemini(self, system: str, prompt: str) -> str:
        full_prompt = f"{system}\n\n{prompt}"
        resp = self._model.generate_content(
            full_prompt,
            generation_config={"max_output_tokens": 1500},
            request_options={"timeout": LLM_TIMEOUT_SECONDS},
        )
        return getattr(resp, "text", "") or ""
