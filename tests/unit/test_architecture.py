"""The executable form of §4.1 and the docs/architecture.md §2 dependency rule.

§4.1 says the LLM must not generate valuations, prices, forecasts, or costs. A prose rule
decays; this one cannot. Every module in the calculation layer is parsed and its imports
inspected, so the layer *cannot* call a model even by accident, and a future contributor
who tries gets a failing test rather than a code review comment they might win.

Written before any LLM code exists, deliberately. A constraint added after the thing it
constrains has already been shaped around it.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src" / "pricing_agent"

# The calculation layer: everything a number can come from.
CALCULATION_PACKAGES = ("domain", "simulation")

# Importing any of these from the calculation layer breaks the architecture.
FORBIDDEN_PREFIXES = (
    "anthropic",          # §4.1 -- no model may participate in producing a number
    "openai",
    "pricing_agent.llm",
    "pricing_agent.agents",
    "pricing_agent.skills",
    "pricing_agent.mcp_clients",  # §2 -- domain performs no I/O; skills pass data in
    "requests",
    "httpx",
    "urllib.request",
    "streamlit",          # calculation must not depend on a presentation framework
)


def calculation_modules() -> list[Path]:
    modules: list[Path] = []
    for package in CALCULATION_PACKAGES:
        modules.extend(sorted((SRC / package).rglob("*.py")))
    assert modules, "No calculation modules found; the guard would pass vacuously."
    return modules


def imported_names(tree: ast.AST) -> list[str]:
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relative import, cannot escape the package
                continue
            if node.module:
                names.append(node.module)
    return names


@pytest.mark.parametrize("module", calculation_modules(), ids=lambda p: p.name)
def test_calculation_layer_has_no_forbidden_imports(module: Path) -> None:
    tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
    offenders = [
        name
        for name in imported_names(tree)
        for prefix in FORBIDDEN_PREFIXES
        if name == prefix or name.startswith(prefix + ".")
    ]
    assert not offenders, (
        f"{module.relative_to(SRC)} imports {offenders}. The calculation layer must not "
        "reach a model, an MCP client, or the network (§4.1, architecture.md §2)."
    )


def test_guard_would_actually_catch_a_violation() -> None:
    """A guard that cannot fail proves nothing.

    Feeds the checker a module that imports anthropic and asserts it is flagged.
    """
    tree = ast.parse("import anthropic\nfrom pricing_agent.llm import explain\n")
    names = imported_names(tree)
    offenders = [
        name
        for name in names
        for prefix in FORBIDDEN_PREFIXES
        if name == prefix or name.startswith(prefix + ".")
    ]
    assert set(offenders) == {"anthropic", "pricing_agent.llm"}


def test_domain_may_depend_on_simulation() -> None:
    """The rule forbids reaching *up* the stack, not down.

    domain summarizes draw matrices, so importing simulation is expected and correct.
    Asserted so a future tightening of the guard does not break it silently.
    """
    tree = ast.parse((SRC / "domain" / "sales_forecast.py").read_text(encoding="utf-8"))
    assert any(
        name.startswith("pricing_agent.simulation") for name in imported_names(tree)
    )
