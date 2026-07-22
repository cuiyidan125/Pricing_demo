"""The output-boundary enforcement of §4.1.

`docs/architecture.md` §3.4: every currency figure and duration in generated prose must
appear in the result's `explanation_inputs`. A figure that does not match fails the
response rather than reaching the user.

The check is deliberately strict — a dollar tolerance, nothing more. A model that rounds
$28,963 to "about $29,000" fails it, and the caller falls back to the deterministic
template. That is the correct trade: the alternative is a tolerance wide enough that an
invented figure could slip through, which would make the guard decorative.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# -$5,134 / $28,963 / $28,963.50 / $ 1200 / $-5,134
# The sign is captured on either side of the symbol. An earlier version required a digit
# immediately after "$", which meant negative amounts were not matched at all and so were
# never checked — a gross of -$5,134 could have been narrated as any figure at all.
_CURRENCY = re.compile(r"(-)?\$\s?(-)?(\d[\d,]*(?:\.\d+)?)")
# 31 days / 1 day / -3 days
_DURATION = re.compile(r"(-?\d[\d,]*(?:\.\d+)?)\s*days?\b", re.IGNORECASE)

DOLLAR_TOLERANCE = 1.0
DAY_TOLERANCE = 1.0


@dataclass(frozen=True)
class GuardResult:
    ok: bool
    violations: list[str]

    def reason(self) -> str:
        if self.ok:
            return ""
        return (
            "Generated narrative cited figures absent from the computed result: "
            + ", ".join(self.violations)
        )


def _numbers(pattern: re.Pattern[str], text: str) -> list[float]:
    """Extract signed numbers. The currency pattern carries its sign in groups 1 and 2;
    the duration pattern carries it inline in group 1."""
    out: list[float] = []
    for match in pattern.finditer(text):
        groups = match.groups()
        raw = groups[-1]
        negative = any(g == "-" for g in groups[:-1])
        try:
            value = float(raw.replace(",", ""))
        except ValueError:  # pragma: no cover - regex guarantees numeric
            continue
        out.append(-value if negative else value)
    return out


def allowed_values(explanation_inputs: dict) -> tuple[set[float], set[float]]:
    """Split the allow-list into currency and duration figures."""
    money: set[float] = set()
    days: set[float] = set()
    for entry in explanation_inputs.get("values", []):
        value = entry.get("value")
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            continue
        unit = entry.get("unit")
        if unit == "USD":
            money.add(float(value))
        elif unit == "DAYS":
            days.add(float(value))
        else:
            # Unit-less counts may legitimately appear either way.
            money.add(float(value))
            days.add(float(value))
    return money, days


def _matches(candidate: float, allowed: set[float], tolerance: float) -> bool:
    return any(abs(candidate - value) <= tolerance for value in allowed)


def check(narrative: str, explanation_inputs: dict) -> GuardResult:
    money, days = allowed_values(explanation_inputs)
    violations: list[str] = []

    for amount in _numbers(_CURRENCY, narrative):
        if not _matches(amount, money, DOLLAR_TOLERANCE):
            violations.append(f"${amount:,.0f}")

    for duration in _numbers(_DURATION, narrative):
        if not _matches(duration, days, DAY_TOLERANCE):
            violations.append(f"{duration:,.0f} days")

    return GuardResult(ok=not violations, violations=violations)


def deterministic_summary(explanation_inputs: dict, warnings: list[dict]) -> str:
    """The fallback narrative. Assembled from the allow-list, so it passes by
    construction — and is what the user sees whenever the guard trips."""
    values = {v["label"]: v for v in explanation_inputs.get("values", [])}

    def money(label: str) -> str:
        entry = values.get(label)
        if not entry or not isinstance(entry.get("value"), (int, float)):
            return "not available"
        amount = float(entry["value"])
        # "-$5,134", not "$-5,134".
        return f"-${abs(amount):,.0f}" if amount < 0 else f"${amount:,.0f}"

    def plain(label: str) -> str:
        entry = values.get(label)
        if not entry:
            return "not available"
        value = entry.get("value")
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value)

    lines = [
        f"Recommended price {money('Recommended price')} against a market value of "
        f"{money('Market value')}, using the {plain('Strategy')} strategy.",
        f"Median time to sell is {plain('P50 days to sale')} days, "
        f"{plain('P90 days to sale')} days in the adverse case. "
        f"Median front-end gross is {money('P50 front-end gross')}.",
        f"Break-even is {money('Break-even')} and the minimum safe list price is "
        f"{money('Minimum safe list price')}.",
    ]

    blocking = [w for w in warnings if w.get("blocks_publication")]
    if blocking:
        lines.append(
            "Publication is blocked by: " + ", ".join(w["code"] for w in blocking) + "."
        )
    return " ".join(lines)
