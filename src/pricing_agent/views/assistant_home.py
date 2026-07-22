"""Ask the Dealer AI Assistant — the product's primary entry point.

A **conversation shell, not an agent.** This phase deliberately does not call a model,
route intent, invoke a skill, or produce a number from the text box. Free text is captured
and the user is told plainly that routing is not connected yet, because a shell that
appeared to understand the request and then quietly did nothing would be worse than one
that says so.

The workflow cards are rendered from data passed in by the caller rather than imported
from the registry, so the view stays free of an import cycle with `workflows.registry`.
"""

from __future__ import annotations

from typing import Iterable, NamedTuple

import streamlit as st

from pricing_agent.workflows.context import WorkflowContext

SESSION_KEY = "assistant_request"

SUGGESTED_PROMPTS = (
    "What should I price this vehicle?",
    "What will my inventory look like in the next 30 days?",
    "Which aging vehicles should I promote?",
    "Can I reach 70 percent utilization by the end of a July 4th event?",
)


class WorkflowCard(NamedTuple):
    """The subset of registry metadata this view renders. Passed in, never imported."""

    display_name: str
    description: str
    icon: str
    availability: str
    skills: tuple[str, ...]


def render_assistant_home(
    workflow_context: WorkflowContext | None = None,
    workflows: Iterable[WorkflowCard] = (),
) -> None:
    """Render the assistant entry point."""
    st.title("Ask the Dealer AI Assistant")
    st.caption(
        "Describe a pricing or inventory decision in your own words. The assistant reads "
        "the request, chooses the right dealer workflow, and hands the numbers to a "
        "deterministic engine — it never produces a price itself."
    )

    st.markdown(
        "**What it can help with**\n\n"
        "- What a vehicle is worth and how to price it\n"
        "- How much discount room a vehicle has before it breaks a floor\n"
        "- What the lot will sell and earn over the next 30 and 90 days\n"
        "- Which vehicles carry the most aging and depreciation risk\n"
        "- Whether a sale event can hit a utilization target, and what it would cost"
    )

    request = st.text_area(
        "Your question",
        key="assistant_input",
        placeholder="e.g. This RAV4 has been sitting 37 days — what should I do with it?",
        height=110,
    )

    left, right = st.columns([1, 4])
    submitted = left.button("Analyze", type="primary")
    right.caption("Suggested questions — click to copy into the box above.")

    for prompt in SUGGESTED_PROMPTS:
        st.markdown(f"- _{prompt}_")

    if submitted:
        # Preserved so the next phase can route it. Nothing is inferred from it here.
        st.session_state[SESSION_KEY] = request
        if request.strip():
            st.info(
                "Natural-language workflow routing will be connected in the next phase. "
                "Select a dealer workflow below to continue with the current prototype.",
                icon="🧭",
            )
            with st.expander("What was captured"):
                st.code(request, language=None)
                st.caption(
                    "Held in session state only. No model was called, no skill was "
                    "invoked, and no figure was derived from this text."
                )
        else:
            st.warning("Type a question first, or pick a workflow below.", icon="✍️")
    elif st.session_state.get(SESSION_KEY):
        st.caption(
            f"Last question captured: _{st.session_state[SESSION_KEY][:120]}_ — routing "
            "arrives in the next phase."
        )

    st.divider()

    cards = list(workflows)
    if cards:
        st.subheader("Dealer workflows")
        st.caption("Choose one from the sidebar to continue.")
        columns = st.columns(2)
        for index, card in enumerate(cards):
            with columns[index % 2].container(border=True):
                st.markdown(f"**{card.icon} {card.display_name}**")
                st.caption(card.description)
                if card.skills:
                    st.caption("Uses: " + ", ".join(card.skills))
                if card.availability != "AVAILABLE":
                    st.caption(f"Status: {card.availability.replace('_', ' ').title()}")

    st.info(
        "Prototype on synthetic data. Forecasts are a **configured simulation**, not a "
        "trained prediction, and no price can be published from this application.",
        icon="ℹ️",
    )
