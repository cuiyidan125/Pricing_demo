"""The view layer.

Views are callables the workflow registry binds a context to. These tests cover the
callable contract and the render/calculate boundary; the registry's own shape is covered
in `test_workflows.py`.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from pricing_agent.views import (
    configure_page,
    render_assistant_home,
    render_dashboard,
    render_improve_aging,
    render_promotion_planner,
    render_vehicle_detail,
)
from pricing_agent.workflows import WorkflowContext

REPO_ROOT = Path(__file__).resolve().parents[2]
VIEWS = REPO_ROOT / "src" / "pricing_agent" / "views"

RENDERERS = [
    render_assistant_home,
    render_dashboard,
    render_improve_aging,
    render_promotion_planner,
    render_vehicle_detail,
]


# --- render functions -----------------------------------------------------------------


@pytest.mark.parametrize("func", RENDERERS, ids=lambda f: f.__name__)
def test_render_functions_are_importable_and_callable(func):
    assert callable(func)


@pytest.mark.parametrize("func", RENDERERS, ids=lambda f: f.__name__)
def test_every_render_function_accepts_an_optional_workflow_context(func):
    """The registry binds a context with `functools.partial`, so the parameter has to be
    present and optional on every view."""
    parameter = inspect.signature(func).parameters.get("workflow_context")
    assert parameter is not None, f"{func.__name__} has no workflow_context parameter"
    assert parameter.default is None


@pytest.mark.parametrize(
    "name",
    [
        "ACQUIRE_INVENTORY",
        "PRICE_INVENTORY",
        "MERCHANDISE_INVENTORY",
        "IMPROVE_AGING_INVENTORY",
    ],
)
def test_workflow_context_has_the_four_dealer_workflows(name):
    assert hasattr(WorkflowContext, name)
    assert WorkflowContext[name].value == name


def test_workflow_context_is_a_string_enum():
    """So it serialises into a URL, a cache key, or an audit record without conversion."""
    assert WorkflowContext.PRICE_INVENTORY == "PRICE_INVENTORY"


def test_workflow_context_labels_read_naturally():
    assert WorkflowContext.IMPROVE_AGING_INVENTORY.label == "Improve Aging Inventory"


# --- views render, they do not calculate ----------------------------------------------


def view_modules() -> list[Path]:
    modules = sorted(p for p in VIEWS.glob("*.py"))
    assert modules, "no view modules found; this test would pass vacuously"
    return modules


def imported_modules(path: Path) -> list[str]:
    """Modules a file actually imports.

    Deliberately AST-based rather than a substring scan: these modules discuss their own
    boundaries in their docstrings, and prose describing a rule must not trip it.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            imported.append(node.module)
    return imported


@pytest.mark.parametrize("module", view_modules(), ids=lambda p: p.name)
def test_views_do_not_import_the_calculation_layer(module):
    """Views consume finished skill results. Reaching into `domain` or `simulation` would
    mean a number was being produced in the presentation layer."""
    forbidden = [
        name for name in imported_modules(module)
        if name.startswith(("pricing_agent.domain", "pricing_agent.simulation"))
    ]
    assert not forbidden, f"{module.name} imports the calculation layer: {forbidden}"


def test_page_config_has_one_call_site():
    """With a single entry script there is now exactly one active `set_page_config`
    path — no per-page call competes with it."""
    elsewhere = ["app.py"] + [
        f"src/pricing_agent/views/{m.name}"
        for m in view_modules()
        if m.name != "page_config.py"
    ]
    offenders = [
        path for path in elsewhere
        if "st.set_page_config" in (REPO_ROOT / path).read_text(encoding="utf-8")
    ]
    assert not offenders, f"set_page_config should only be called in page_config.py: {offenders}"

    # Count real calls, not string occurrences — the module's own docstring names it.
    tree = ast.parse((VIEWS / "page_config.py").read_text(encoding="utf-8"))
    calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "set_page_config"
    ]
    assert len(calls) == 1, "exactly one call site, inside configure_page"
    assert callable(configure_page)


def test_views_do_not_import_the_registry():
    """The registry imports views to bind render callables. A dependency back the other
    way would close an import cycle — the assistant takes its cards as an argument
    instead."""
    for module in view_modules():
        imported = imported_modules(module)
        offenders = [name for name in imported if name.startswith("pricing_agent.workflows.registry")]
        assert not offenders, f"{module.name} imports the registry: {offenders}"
