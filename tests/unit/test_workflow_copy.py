"""Workflow-specific page copy.

Phase 3.1 is presentation-only: a view rendered for a workflow says the workflow's name,
and says nothing about a capability the engine does not have. These tests hold both halves
of that — the copy is right, and nothing underneath it moved.
"""

from __future__ import annotations

import ast
import inspect
import subprocess
from pathlib import Path

import pytest

from pricing_agent.views.workflow_copy import (
    WORKFLOW_COPY,
    WorkflowCopy,
    copy_for,
    render_workflow_header,
)
from pricing_agent.workflows.context import WorkflowContext
from pricing_agent.workflows.registry import DEALER_WORKFLOWS, by_id

REPO_ROOT = Path(__file__).resolve().parents[2]
VIEWS = REPO_ROOT / "src" / "pricing_agent" / "views"

EXPECTED_TITLES = {
    WorkflowContext.ACQUIRE_INVENTORY: "Acquire Inventory",
    WorkflowContext.PRICE_INVENTORY: "Price Inventory",
    WorkflowContext.MERCHANDISE_INVENTORY: "Merchandise Inventory",
    WorkflowContext.IMPROVE_AGING_INVENTORY: "Improve Aging Inventory",
}


# --- each context produces the right title --------------------------------------------


@pytest.mark.parametrize(
    ("context", "title"), EXPECTED_TITLES.items(), ids=lambda v: getattr(v, "value", v)
)
def test_each_workflow_context_produces_its_title(context, title):
    assert copy_for(context).title == title


def test_every_workflow_context_has_copy():
    assert set(WORKFLOW_COPY) == set(WorkflowContext)


@pytest.mark.parametrize("context", list(WorkflowContext), ids=lambda c: c.value)
def test_every_entry_has_a_non_empty_title_and_subtitle(context):
    copy = WORKFLOW_COPY[context]
    assert copy.title.strip()
    assert copy.subtitle.strip()
    assert copy.subtitle != copy.title, "the subtitle must say something the title does not"


def test_titles_match_the_registry_display_names():
    """Copy and navigation must not drift — the sidebar entry and the page heading are the
    same words or the user has to guess which page they landed on."""
    for definition in DEALER_WORKFLOWS:
        assert copy_for(definition.context).title == definition.display_name


def test_no_workflow_context_falls_back_to_generic_copy():
    assert copy_for(None) is None


def test_copy_table_is_immutable():
    """A view must not be able to rewrite another workflow's heading at runtime."""
    with pytest.raises(TypeError):
        WORKFLOW_COPY[WorkflowContext.PRICE_INVENTORY] = WorkflowCopy("x", "y")
    with pytest.raises(Exception):
        copy_for(WorkflowContext.PRICE_INVENTORY).title = "x"


# --- Acquire does not overclaim --------------------------------------------------------


def test_acquire_copy_does_not_claim_external_candidate_appraisal():
    copy = copy_for(WorkflowContext.ACQUIRE_INVENTORY)
    blob = " ".join(
        part for part in (copy.title, copy.subtitle, copy.instruction, copy.scope_note) if part
    ).lower()

    for claim in (
        "appraise a vehicle you are considering",
        "value a vehicle before you buy",
        "evaluate an acquisition candidate",
        "should i buy this",
        "auction",
        "trade-in appraisal",
    ):
        assert claim not in blob, f"Acquire copy implies external appraisal: {claim!r}"


def test_acquire_copy_states_the_limit_explicitly():
    """Not overclaiming is not enough — the page has to say what it will not do, because
    the workflow's own name is what creates the wrong expectation."""
    copy = copy_for(WorkflowContext.ACQUIRE_INVENTORY)
    assert copy.scope_note, "Acquire Inventory must carry a scope note"
    note = copy.scope_note.lower()
    assert "not" in note
    assert "external" in note and "appraise" in note


def test_acquire_copy_is_about_capacity_and_aging():
    subtitle = copy_for(WorkflowContext.ACQUIRE_INVENTORY).subtitle.lower()
    assert "capacity" in subtitle
    assert "aging" in subtitle


def test_improve_aging_copy_names_all_three_capabilities():
    subtitle = copy_for(WorkflowContext.IMPROVE_AGING_INVENTORY).subtitle.lower()
    for capability in ("portfolio forecasting", "single-vehicle", "promotion planning"):
        assert capability in subtitle
    assert copy_for(WorkflowContext.IMPROVE_AGING_INVENTORY).scope_note


# --- the views ask for copy rather than branching on names -----------------------------


def view_modules() -> list[Path]:
    modules = sorted(p for p in VIEWS.glob("*.py"))
    assert modules, "no view modules found; this test would pass vacuously"
    return modules


# The copy table itself names every workflow. The assistant is the router's view: its
# whole job is to dispatch result rendering by workflow, so branching on workflow identity
# there is the design, not the smell this test guards against.
_WORKFLOW_BRANCHING_ALLOWED = {"workflow_copy.py", "assistant_home.py"}


@pytest.mark.parametrize("module", view_modules(), ids=lambda p: p.name)
def test_views_do_not_compare_raw_workflow_names(module):
    """No `if workflow_context == "PRICE_INVENTORY"` scattered through the views. Copy
    selection lives in one typed table; a view looks its heading up."""
    if module.name in _WORKFLOW_BRANCHING_ALLOWED:
        return

    source = module.read_text(encoding="utf-8")
    for context in WorkflowContext:
        assert f'"{context.value}"' not in source, f"{module.name} compares a raw name"
        assert f"WorkflowContext.{context.name}" not in source, (
            f"{module.name} branches on {context.name}; use workflow_copy instead"
        )


@pytest.mark.parametrize(
    "module",
    [p for p in view_modules() if p.name in {"dashboard.py", "promotion.py", "vehicle_detail.py", "improve_aging.py"}],
    ids=lambda p: p.name,
)
def test_workflow_views_render_their_heading_through_the_shared_helper(module):
    source = module.read_text(encoding="utf-8")
    assert "render_workflow_header" in source


def test_render_workflow_header_falls_back_without_a_context(monkeypatch):
    """Requirement 5: a view rendered with no workflow keeps its generic copy."""
    printed: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "pricing_agent.views.workflow_copy.st.title",
        lambda text: printed.append(("title", text)),
    )
    monkeypatch.setattr(
        "pricing_agent.views.workflow_copy.st.caption",
        lambda text: printed.append(("caption", text)),
    )

    assert render_workflow_header(None, fallback_title="Used Vehicle Pricing Advisor") is None
    assert printed == [("title", "Used Vehicle Pricing Advisor")]

    printed.clear()
    copy = render_workflow_header(WorkflowContext.PRICE_INVENTORY)
    assert copy is copy_for(WorkflowContext.PRICE_INVENTORY)
    assert printed == [("title", "Price Inventory"), ("caption", copy.subtitle)]


def test_a_view_with_no_context_and_no_fallback_prints_no_heading(monkeypatch):
    """Vehicle detail had no page-level title before this phase; without a workflow it
    must still lead with the vehicle rather than gaining an empty heading."""
    calls: list[str] = []
    monkeypatch.setattr(
        "pricing_agent.views.workflow_copy.st.title", lambda text: calls.append(text)
    )
    monkeypatch.setattr(
        "pricing_agent.views.workflow_copy.st.caption", lambda text: calls.append(text)
    )
    assert render_workflow_header(None) is None
    assert calls == []


# --- the views still work, and nothing underneath them moved ---------------------------


@pytest.mark.parametrize(
    "workflow_id", ["price-inventory", "merchandise-inventory", "acquire-inventory"]
)
def test_workflow_views_remain_bindable_and_keep_their_signature(workflow_id):
    definition = by_id(workflow_id)
    parameter = inspect.signature(definition.render).parameters.get("workflow_context")
    assert parameter is not None and parameter.default is None
    assert callable(definition.bound_render())


@pytest.mark.parametrize(
    ("module", "expected"),
    [
        ("dashboard.py", ("load_config", "portfolio", "inventory")),
        ("promotion.py", ("events", "plan")),
        ("vehicle_detail.py", ("analyze_vehicle", "load_inventory", "explain")),
    ],
)
def test_views_still_call_the_same_data_and_skill_entry_points(module, expected):
    """Copy changed; what the page runs did not."""
    source = (VIEWS / module).read_text(encoding="utf-8")
    for symbol in expected:
        assert f"{symbol}(" in source, f"{module} no longer calls {symbol}()"


def test_copy_module_contains_no_calculation():
    source = (VIEWS / "workflow_copy.py").read_text(encoding="utf-8")
    for banned in ("simulate(", "percentile", "np.", "numpy", "pandas", "analyze(", "plan("):
        assert banned not in source, f"copy module should not reference {banned}"


def test_copy_module_imports_nothing_below_the_view_layer():
    tree = ast.parse((VIEWS / "workflow_copy.py").read_text(encoding="utf-8"))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            imported.append(node.module)

    forbidden = [
        name for name in imported
        if name.startswith(
            (
                "pricing_agent.domain",
                "pricing_agent.simulation",
                "pricing_agent.policy",
                "pricing_agent.skills",
                "pricing_agent.mcp_clients",
            )
        )
    ]
    assert not forbidden, f"copy module reaches below the view layer: {forbidden}"


# --- the phase's own boundary ----------------------------------------------------------

PROTECTED = (
    "skills/",
    "schemas/",
    "mocks/",
    "config/",
    "src/pricing_agent/skills/",
    "src/pricing_agent/domain/",
    "src/pricing_agent/simulation/",
    "src/pricing_agent/policy/",
    "src/pricing_agent/mcp_clients/",
)


def test_no_calculation_or_skill_module_was_modified_in_this_phase():
    """Presentation-only, checked against git rather than asserted in prose.

    Skipped outside a git checkout so the suite still runs from an export.
    """
    try:
        changed = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all", "--", *PROTECTED],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):  # pragma: no cover - no git available
        pytest.skip("git not available")

    if changed.returncode != 0:  # pragma: no cover - not a checkout
        pytest.skip("not a git checkout")

    assert not changed.stdout.strip(), (
        "Phase 3.1 is presentation-only, but these are modified:\n" + changed.stdout
    )
