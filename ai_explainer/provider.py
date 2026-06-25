"""
ai_explainer/provider.py — Swappable LLM provider.

The whole point: the rest of StatMind calls `explain()` and never knows or cares
whether the model is a hosted API (Anthropic/OpenAI) or a local model running on
your own box (e.g. an Oracle ARM instance with a quantized 7B). Switch by the
LLM_PROVIDER env var; no feature code changes.

WHY THIS DESIGN
---------------
* Hosted-first (recommended): ship a fast, reliably-grounded explainer now.
* Local-swappable (later): the day a regulated customer needs "data never leaves
  our infrastructure", set LLM_PROVIDER=local and point it at your own model.
  The grounding/safety layer is identical either way.

PRIVACY NOTE
------------
When LLM_PROVIDER is a hosted API, the grounding payload (verified scalar facts —
NOT raw uploaded data) is sent to that provider. Use a no-training/no-retention
tier and disclose this on the security page. The grounding layer deliberately
sends only computed scalars (Cpk, verdict, etc.), never the user's raw rows.

CREDENTIALS
-----------
API keys are read from environment variables ONLY. This module never hardcodes,
logs, or echoes a key. Set them in your deployment environment, not in code.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class ExplainResult:
    ok: bool
    text: str = ""
    provider: str = ""
    error: str = ""


class LLMProvider:
    """Base interface. A provider turns a message list into a text response."""
    name = "base"

    def complete(self, messages: list[dict], *, max_tokens: int = 600) -> ExplainResult:
        raise NotImplementedError


class HostedAnthropicProvider(LLMProvider):
    """Hosted Claude via the Anthropic API. Requires ANTHROPIC_API_KEY in env."""
    name = "anthropic"

    def __init__(self, model: str = "claude-sonnet-4-6"):
        self.model = model

    def complete(self, messages: list[dict], *, max_tokens: int = 600) -> ExplainResult:
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if not api_key:
            return ExplainResult(False, provider=self.name,
                                 error="ANTHROPIC_API_KEY not set in environment.")
        try:
            # Imported lazily so the package isn't a hard dependency when using
            # a different provider.
            import anthropic
        except ImportError:
            return ExplainResult(False, provider=self.name,
                                 error="anthropic package not installed.")
        # Anthropic API wants the system prompt separate from the messages.
        system = next((m["content"] for m in messages if m["role"] == "system"), "")
        chat = [m for m in messages if m["role"] != "system"]
        try:
            client = anthropic.Anthropic(api_key=api_key)
            resp = client.messages.create(
                model=self.model, max_tokens=max_tokens,
                system=system, messages=chat,
            )
            text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
            return ExplainResult(True, text=text, provider=self.name)
        except Exception as e:
            # Never leak data: log/return only the error TYPE.
            return ExplainResult(False, provider=self.name,
                                 error=f"{type(e).__name__} from provider.")


class LocalModelProvider(LLMProvider):
    """Placeholder for a self-hosted model (e.g. quantized 7B on an Oracle ARM
    instance via an OpenAI-compatible local server like llama.cpp / Ollama).

    Wire this up when/if you need data to never leave your infrastructure. It is
    intentionally a stub now: the abstraction exists so switching is a config
    change, not a rewrite.
    """
    name = "local"

    def __init__(self, endpoint: Optional[str] = None):
        self.endpoint = endpoint or os.getenv("LOCAL_LLM_ENDPOINT", "")

    def complete(self, messages: list[dict], *, max_tokens: int = 600) -> ExplainResult:
        if not self.endpoint:
            return ExplainResult(
                False, provider=self.name,
                error="Local model not configured (set LOCAL_LLM_ENDPOINT).",
            )
        # Intentionally not implemented yet — documented path for later.
        return ExplainResult(
            False, provider=self.name,
            error="Local provider is a stub. Implement against your local "
                  "OpenAI-compatible endpoint when on-prem is required.",
        )


def get_provider() -> LLMProvider:
    """Select the provider from env. Defaults to hosted Anthropic."""
    choice = os.getenv("LLM_PROVIDER", "anthropic").strip().lower()
    if choice == "local":
        return LocalModelProvider()
    # default / "anthropic"
    model = os.getenv("LLM_MODEL", "claude-sonnet-4-6")
    return HostedAnthropicProvider(model=model)
