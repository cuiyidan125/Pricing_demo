"""Anthropic client wiring and the live/recorded switch.

A live demo must not be able to break. Every call through this module either returns
a model response or falls back to a pre-recorded one from `mocks/llm/`, and the UI is
told which happened so it can say so honestly rather than passing off a recording as
live.

This module — and everything else under `llm/` and `agents/` — is invisible to the
calculation layer. `tests/unit/test_architecture.py` fails the build if anything in
`domain/` or `simulation/` imports it.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pricing_agent.config.loader import REPO_ROOT

MODEL = "claude-opus-4-8"
RECORDINGS = REPO_ROOT / "mocks" / "llm"


@dataclass(frozen=True)
class LlmResult:
    """A model response, or the recording that stood in for one."""

    content: Any
    live: bool
    note: str = ""

    @property
    def source_label(self) -> str:
        return "live" if self.live else "recorded"


def credentials_present() -> bool:
    """Best-effort check for usable credentials.

    An unset ANTHROPIC_API_KEY does not mean there are no credentials — the SDK also
    resolves an `ant auth login` profile — so both are checked. This is only used to
    decide whether to *attempt* a call; every call still falls back on failure.
    """
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return True
    config_dir = Path(
        os.environ.get("ANTHROPIC_CONFIG_DIR", Path.home() / ".config" / "anthropic")
    )
    return (config_dir / "credentials").exists()


def _client():
    import anthropic  # imported lazily so the app runs without the SDK installed

    return anthropic.Anthropic()


def load_recording(name: str) -> Any:
    path = RECORDINGS / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"No recorded fallback for {name!r} at {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def complete(
    *,
    system: str,
    user: str,
    recording: str,
    max_tokens: int = 4096,
    output_schema: dict | None = None,
) -> LlmResult:
    """One request, with a recorded fallback on any failure.

    `output_schema` uses structured outputs, which is what makes §4.2 enforceable at the
    boundary: the model cannot return anything but the declared shape, and the caller
    still validates the result against the real request schema afterwards.
    """
    if not credentials_present():
        return LlmResult(
            load_recording(recording), live=False, note="No API credentials found."
        )

    try:
        kwargs: dict[str, Any] = {
            "model": MODEL,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        if output_schema is not None:
            kwargs["output_config"] = {
                "format": {"type": "json_schema", "schema": output_schema}
            }

        response = _client().messages.create(**kwargs)

        if response.stop_reason == "refusal":
            return LlmResult(
                load_recording(recording),
                live=False,
                note="The model declined this request.",
            )

        text = next((b.text for b in response.content if b.type == "text"), "")
        content = json.loads(text) if output_schema is not None else text
        return LlmResult(content, live=True)

    except Exception as exc:  # noqa: BLE001 - a demo must degrade, never crash
        return LlmResult(
            load_recording(recording),
            live=False,
            note=f"{type(exc).__name__}: {exc}",
        )
