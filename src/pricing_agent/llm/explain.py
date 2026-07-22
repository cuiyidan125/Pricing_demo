"""Narration. Consumes a finished result; never participates in producing one.

The fallback is a **deterministic template assembled from `explanation_inputs`**, not a
recorded narrative. A recording made for one vehicle would cite that vehicle's figures and
fail the guard on any other, so it would be worse than useless. The template passes by
construction, which means the degraded path is always correct rather than merely available.

Three things can happen, and the UI is told which:

  live + guard passed   -> the model's prose
  live + guard failed   -> the template, and the rejected figures are surfaced
  no credentials        -> the template
"""

from __future__ import annotations

from dataclasses import dataclass

from pricing_agent.agents import narration_guard
from pricing_agent.llm import prompts
from pricing_agent.llm.client import complete, credentials_present


@dataclass(frozen=True)
class Narrative:
    text: str
    live: bool
    guard_passed: bool
    note: str = ""
    rejected: tuple[str, ...] = ()

    @property
    def source_label(self) -> str:
        if self.live and self.guard_passed:
            return "live"
        if self.live and not self.guard_passed:
            return "template (model output rejected)"
        return "template"


def explain(
    explanation_inputs: dict,
    warnings: list[dict],
    question: str | None = None,
) -> Narrative:
    """Narrate a result, falling back to the deterministic template when necessary."""
    template = narration_guard.deterministic_summary(explanation_inputs, warnings)

    if not credentials_present():
        return Narrative(
            text=template,
            live=False,
            guard_passed=True,
            note="No API credentials; using the deterministic template.",
        )

    result = complete(
        system=prompts.EXPLANATION_SYSTEM,
        user=prompts.explanation_user_message(
            explanation_inputs.get("values", []), warnings, question
        ),
        recording="explanation_fallback",
        max_tokens=1024,
    )

    if not result.live or not isinstance(result.content, str):
        return Narrative(
            text=template, live=False, guard_passed=True, note=result.note
        )

    report = narration_guard.check(result.content, explanation_inputs)
    if not report.ok:
        # The model cited something the engine never published. Discard it — this is the
        # failure mode §4.1 exists to prevent, and showing it anyway would make the whole
        # architectural claim decorative.
        return Narrative(
            text=template,
            live=True,
            guard_passed=False,
            note=report.reason(),
            rejected=tuple(report.violations),
        )

    return Narrative(text=result.content, live=True, guard_passed=True)
