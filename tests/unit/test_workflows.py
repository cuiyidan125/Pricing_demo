"""The workflow registry and the agent-first navigation shell.

The registry is the single declaration of what the product offers, so most of these tests
are about shape and boundaries: workflows are dealer jobs, skills stay underneath them,
and the assistant shell does not quietly do more than it claims.
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

from pricing_agent.views.assistant_home import SESSION_KEY, SUGGESTED_PROMPTS
from pricing_agent.workflows import WorkflowContext
from pricing_agent.workflows.registry import (
    ASSISTANT,
    DEALER_WORKFLOWS,
    WORKFLOWS,
    Availability,
    NavigationGroup,
    SkillId,
    by_id,
    grouped,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
VIEWS = REPO_ROOT / "src" / "pricing_agent" / "views"
WORKFLOWS_DIR = REPO_ROOT / "src" / "pricing_agent" / "workflows"

def imported_modules(path: Path) -> list[str]:
    """Modules a file actually imports, ignoring any mention of one in prose."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            imported.append(node.module)
    return imported


EXPECTED_WORKFLOW_IDS = {
    "ask-the-assistant",
    "acquire-inventory",
    "price-inventory",
    "merchandise-inventory",
    "improve-aging-inventory",
}


# --- registry completeness ------------------------------------------------------------


def test_registry_contains_the_assistant_and_four_dealer_workflows():
    assert {d.workflow_id for d in WORKFLOWS} == EXPECTED_WORKFLOW_IDS
    assert len(DEALER_WORKFLOWS) == 4


@pytest.mark.parametrize("definition", WORKFLOWS, ids=lambda d: d.workflow_id)
def test_every_entry_is_fully_specified(definition):
    assert definition.display_name and definition.description
    assert definition.navigation.title and definition.navigation.url_path
    assert definition.navigation.icon
    assert isinstance(definition.navigation.group, NavigationGroup)
    assert isinstance(definition.availability, Availability)
    assert definition.disclaimer, "every entry must carry a prototype disclaimer"


def test_workflow_ids_are_unique():
    ids = [d.workflow_id for d in WORKFLOWS]
    assert len(ids) == len(set(ids))


def test_url_paths_are_unique():
    paths = [d.navigation.url_path for d in WORKFLOWS]
    assert len(paths) == len(set(paths))


@pytest.mark.parametrize("definition", WORKFLOWS, ids=lambda d: d.workflow_id)
def test_every_render_callable_is_importable_and_bindable(definition):
    assert callable(definition.render)
    assert callable(definition.bound_render())


def test_by_id_round_trips_and_rejects_unknown():
    assert by_id("price-inventory").display_name == "Price Inventory"
    with pytest.raises(KeyError):
        by_id("not-a-workflow")


# --- navigation shape -----------------------------------------------------------------


def test_ask_the_assistant_is_the_default_page():
    defaults = [d for d in WORKFLOWS if d.navigation.default]
    assert len(defaults) == 1, "exactly one default page"
    assert defaults[0].workflow_id == "ask-the-assistant"
    assert ASSISTANT.navigation.group is NavigationGroup.DEALER_AI_ASSISTANT


def test_navigation_has_exactly_two_groups():
    assert set(grouped()) == {
        NavigationGroup.DEALER_AI_ASSISTANT,
        NavigationGroup.DEALER_WORKFLOWS,
    }


def test_skills_are_not_top_level_navigation_entries():
    """Skills are reusable capabilities underneath workflows, never peers of them."""
    titles = {d.navigation.title.lower() for d in WORKFLOWS}
    for skill in SkillId:
        readable = skill.value.replace("-", " ")
        assert readable not in titles, f"{skill.value} must not be a navigation entry"

    groups = {group.value.lower() for group in NavigationGroup}
    assert "skills" not in groups


def test_every_dealer_workflow_carries_a_context():
    for definition in DEALER_WORKFLOWS:
        assert isinstance(definition.context, WorkflowContext)


def test_the_assistant_sits_above_the_workflows_and_has_no_context():
    assert ASSISTANT.context is None
    assert ASSISTANT.skills == ()


# --- page reuse -----------------------------------------------------------------------


def test_the_same_render_function_can_be_bound_to_different_contexts():
    """The mechanism that lets one view serve several workflows without duplication."""
    from pricing_agent.views.dashboard import render_dashboard
    from pricing_agent.workflows.registry import NavigationEntry, WorkflowDefinition

    def make(context: WorkflowContext) -> WorkflowDefinition:
        return WorkflowDefinition(
            workflow_id=f"probe-{context.value.lower()}",
            display_name="probe",
            description="probe",
            navigation=NavigationEntry(
                title="probe",
                url_path=f"probe-{context.value.lower()}",
                icon=":material/science:",
                group=NavigationGroup.DEALER_WORKFLOWS,
            ),
            render=render_dashboard,
            context=context,
        )

    acquire = make(WorkflowContext.ACQUIRE_INVENTORY)
    aging = make(WorkflowContext.IMPROVE_AGING_INVENTORY)

    assert acquire.render is aging.render, "same view function, not a copy"
    assert acquire.bound_render().keywords["workflow_context"] is WorkflowContext.ACQUIRE_INVENTORY
    assert aging.bound_render().keywords["workflow_context"] is WorkflowContext.IMPROVE_AGING_INVENTORY


# --- Improve Aging is a workflow, not a skill -----------------------------------------


def test_improve_aging_is_a_workflow_that_reuses_all_three_skills():
    definition = by_id("improve-aging-inventory")
    assert definition.context is WorkflowContext.IMPROVE_AGING_INVENTORY
    assert set(definition.skills) == set(SkillId), "it coordinates all three"
    assert definition.availability is Availability.SHELL_ONLY
    assert "orchestration" in definition.disclaimer.lower()


def test_improve_aging_did_not_become_a_fourth_skill():
    assert len(SkillId) == 3
    assert {s.value for s in SkillId} == {
        "single-vehicle-valuation",
        "inventory-portfolio-forecast",
        "dealer-event-promotion-planner",
    }
    # The three SKILL.md specifications are untouched and still the only ones.
    specs = sorted(p.parent.name for p in (REPO_ROOT / "skills").glob("*/SKILL.md"))
    assert specs == [
        "dealer-event-promotion-planner",
        "inventory-portfolio-forecast",
        "single-vehicle-valuation",
    ]


# --- WorkflowContext moved out of views -----------------------------------------------


def test_workflow_context_lives_in_the_workflow_package():
    assert WorkflowContext.__module__ == "pricing_agent.workflows.context"


def test_views_no_longer_define_a_context_module():
    assert not (VIEWS / "context.py").exists(), "views/context.py should have moved"
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("pricing_agent.views.context")


def test_no_module_still_imports_the_old_location():
    """AST-based, not a substring scan: `workflows/context.py` documents where it moved
    from, and a docstring explaining the move is not a stale import."""
    offenders = []
    for path in REPO_ROOT.rglob("*.py"):
        if {".git", ".venv", "venv", "site-packages"} & set(path.parts):
            continue
        if any(
            name.startswith("pricing_agent.views.context")
            for name in imported_modules(path)
        ):
            offenders.append(path.relative_to(REPO_ROOT))
    assert not offenders, f"stale imports: {offenders}"


# --- boundaries -----------------------------------------------------------------------


def python_files(directory: Path) -> list[Path]:
    files = sorted(directory.glob("*.py"))
    assert files, f"no modules under {directory}; this test would pass vacuously"
    return files


@pytest.mark.parametrize(
    "module", python_files(WORKFLOWS_DIR) + python_files(VIEWS), ids=lambda p: p.name
)
def test_no_workflow_or_view_touches_the_calculation_layer(module):
    """Workflows sequence and views render. Neither may produce a number."""
    forbidden = [
        name for name in imported_modules(module)
        if name.startswith(("pricing_agent.domain", "pricing_agent.simulation"))
    ]
    assert not forbidden, f"{module.name} imports the calculation layer: {forbidden}"


def test_the_registry_holds_no_calculation():
    source = (WORKFLOWS_DIR / "registry.py").read_text(encoding="utf-8")
    for banned in ("simulate(", "percentile", "np.", "numpy", "pandas"):
        assert banned not in source, f"registry should not reference {banned}"


# --- the assistant shell does not overreach -------------------------------------------


def test_assistant_page_calls_no_model_and_publishes_nothing():
    """Phase 4 routes and executes — deterministically. It may reach the agent layer, but
    never a model and never the write path."""
    source = (VIEWS / "assistant_home.py").read_text(encoding="utf-8")
    for banned in (
        "pricing_agent.llm",
        "anthropic",
        "openai",
        "publish_vehicle_price",
        "save_pricing_decision",
    ):
        assert banned not in source, f"assistant page must not reference {banned}"


def test_assistant_routes_through_the_deterministic_agent():
    source = (VIEWS / "assistant_home.py").read_text(encoding="utf-8")
    assert "run_assistant" in source, "the page must call the deterministic orchestrator"
    assert SESSION_KEY in source
    assert "st.session_state" in source
    # The Phase 3 shell disclaimer is gone: routing is connected now.
    assert "will be connected in the next phase" not in source


def test_assistant_offers_four_suggested_prompts_that_route():
    assert len(SUGGESTED_PROMPTS) == 4
    joined = " ".join(SUGGESTED_PROMPTS).lower()
    # One prompt per supported destination, plus the deferred aging case.
    for fragment in ("f-150", "next 30 days", "summer clearance", "aging vehicles"):
        assert fragment in joined


def test_improve_aging_page_fabricates_no_output():
    source = (VIEWS / "improve_aging.py").read_text(encoding="utf-8")
    assert "next phase" in source
    for banned in ("pricing_agent.skills", "analyze(", "plan_event("):
        assert banned not in source, "the placeholder must not invoke a skill"


# --- legacy navigation is gone --------------------------------------------------------


def test_legacy_filesystem_pages_are_not_simultaneously_active():
    """Streamlit ignores `pages/` once st.navigation is used, but leaving the directory
    would invite confusion about which navigation is live."""
    assert not (REPO_ROOT / "pages").exists(), "pages/ should have been removed"
    assert not (REPO_ROOT / "spike_navigation.py").exists(), "the spike should be removed"


def test_entry_point_builds_navigation_from_the_registry():
    source = (REPO_ROOT / "app.py").read_text(encoding="utf-8")
    assert "st.navigation" in source
    assert "grouped()" in source, "navigation must come from the registry, not literals"
    assert "configure_page" in source
    assert "st.set_page_config" not in source, "page config belongs to views.page_config"
