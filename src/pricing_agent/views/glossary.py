"""The shared "How to read these estimates" expander.

One renderer so every page presents the same brief, business-worded glossary. The definitions
live in `terminology.GLOSSARY`; this only lays them out inside a collapsed expander.
"""

from __future__ import annotations

import streamlit as st

from pricing_agent.views import terminology as T


def render_glossary(extra_note: str | None = None) -> None:
    with st.expander(T.GLOSSARY_TITLE):
        for term, definition in T.GLOSSARY:
            st.markdown(f"**{term}** — {definition}")
        if extra_note:
            st.caption(extra_note)
