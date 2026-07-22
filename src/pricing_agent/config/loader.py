"""Load every prototype assumption from config/assumptions/.

§28 requires all numerical assumptions to be centralized in configurable files rather
than distributed as hard-coded constants. This module is the only place that reads them,
and `Config.version_stamps()` supplies the values §23 requires in every audit record.

Nothing here is calibrated. See docs/open-questions.md C2.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
ASSUMPTIONS_DIR = REPO_ROOT / "config" / "assumptions"
MOCKS_DIR = REPO_ROOT / "mocks"
SCHEMAS_DIR = REPO_ROOT / "schemas"

_FILES = (
    "valuation",
    "pricing",
    "discounting",
    "holding_cost",
    "depreciation",
    "simulation",
    "portfolio",
    "promotion",
    "freshness",
    "warnings",
)


@dataclass(frozen=True)
class Config:
    """Immutable view over config/assumptions/."""

    valuation: Mapping[str, Any]
    pricing: Mapping[str, Any]
    discounting: Mapping[str, Any]
    holding_cost: Mapping[str, Any]
    depreciation: Mapping[str, Any]
    simulation: Mapping[str, Any]
    portfolio: Mapping[str, Any]
    promotion: Mapping[str, Any]
    freshness: Mapping[str, Any]
    warnings: Mapping[str, Any]
    version: Mapping[str, Any]

    @property
    def config_version(self) -> str:
        return self.version["config_version"]

    @property
    def assumption_version(self) -> str:
        return self.version["assumption_version"]

    @property
    def model_version(self) -> str:
        return self.version["model_version"]

    @property
    def model_label(self) -> str:
        # §16.2: must never be represented as a trained production prediction.
        return self.version["model_label"]

    def version_stamps(self) -> dict[str, str]:
        """The §23 audit fields describing which assumptions produced a result."""
        return {
            "config_version": self.config_version,
            "assumption_version": self.assumption_version,
            "model_version": self.model_version,
            "model_label": self.model_label,
        }


@lru_cache(maxsize=1)
def load_config(assumptions_dir: Path | None = None) -> Config:
    """Load and cache the assumption set."""
    directory = assumptions_dir or ASSUMPTIONS_DIR
    loaded: dict[str, Any] = {}
    for name in _FILES:
        path = directory / f"{name}.yaml"
        if not path.exists():
            raise FileNotFoundError(f"Missing assumption file: {path}")
        loaded[name] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    loaded["version"] = yaml.safe_load(
        (directory / "VERSION.yaml").read_text(encoding="utf-8")
    )
    return Config(**loaded)


# --- lookup helpers -------------------------------------------------------------------


def interpolate(table: Mapping[float, float], x: float) -> float:
    """Piecewise-linear interpolation over a numerically keyed map, clamped at the ends.

    simulation.yaml expresses the price-position and supply multipliers as sparse maps
    (`0.90: 1.55`, `0.95: 1.28`, ...). PyYAML parses those keys as floats, so a plain
    lookup only works for values that happen to land exactly on a key. Interpolating
    keeps the response continuous, which matters because the discount ladder walks
    price-to-market in $250 steps and a step function would produce an argmax that
    reflects the table's granularity rather than the vehicle's economics.
    """
    if not table:
        raise ValueError("Cannot interpolate an empty table")

    keys = sorted(float(k) for k in table.keys())
    if x <= keys[0]:
        return float(table[_key_of(table, keys[0])])
    if x >= keys[-1]:
        return float(table[_key_of(table, keys[-1])])

    for low, high in zip(keys, keys[1:]):
        if low <= x <= high:
            y_low = float(table[_key_of(table, low)])
            y_high = float(table[_key_of(table, high)])
            if high == low:
                return y_low
            weight = (x - low) / (high - low)
            return y_low + weight * (y_high - y_low)

    raise AssertionError("unreachable")  # pragma: no cover


def _leading_number(text: str) -> float | None:
    """Pull the threshold out of a band-key remainder like `30000` or `2_years`."""
    match = re.match(r"^(\d+(?:\.\d+)?)", text)
    return float(match.group(1)) if match else None


def _key_of(table: Mapping[Any, Any], value: float) -> Any:
    """Recover the original key object for a float value (keys may be int or float)."""
    for key in table:
        if float(key) == value:
            return key
    raise KeyError(value)


def banded_lookup(bands: Mapping[str, Any], value: float, default: float) -> float:
    """Resolve an `under_X` / `over_X` style band map.

    Used by the mileage and vehicle-age multipliers, which are expressed as ordered
    thresholds rather than numeric keys. Keys may carry a unit suffix
    (`under_2_years` as well as `under_30000`), so the threshold is the leading number
    rather than the whole remainder.
    """
    unders = []
    overs = []
    for name, factor in bands.items():
        if name.startswith("under_"):
            threshold = _leading_number(name.removeprefix("under_"))
            if threshold is not None:
                unders.append((threshold, factor))
        elif name.startswith("over_"):
            threshold = _leading_number(name.removeprefix("over_"))
            if threshold is not None:
                overs.append((threshold, factor))

    for threshold, factor in sorted(unders):
        if value < threshold:
            return float(factor)
    for threshold, factor in sorted(overs, reverse=True):
        if value >= threshold:
            return float(factor)
    return float(default)


def expected_discount_rate(
    config: Config, segment: str, price: float, override: float | None = None
) -> float:
    """The D4 assumption underneath minimum safe list price and all headroom.

    An override is honoured when a dealer supplies one; otherwise the segment and price
    band decide, falling back to the global default. This single number sits beneath
    every floor and headroom figure in the system and is not calibrated — §27 item 13
    requires it be surfaced in the UI rather than buried here.
    """
    if override is not None:
        return float(override)

    default = float(config.discounting["default_expected_discount_rate"])
    by_segment = config.discounting.get("by_segment", {})
    bands = config.discounting.get("price_bands", {})

    segment_bands = by_segment.get(segment)
    if not segment_bands:
        return default

    # Choose the narrowest band whose range contains the price.
    best: tuple[float, float] | None = None
    for band_name, rate in segment_bands.items():
        bounds = bands.get(band_name)
        if not bounds:
            continue
        low, high = float(bounds[0]), float(bounds[1])
        if low <= price < high:
            width = high - low
            if best is None or width < best[0]:
                best = (width, float(rate))

    return best[1] if best else default
