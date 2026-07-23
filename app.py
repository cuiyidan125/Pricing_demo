"""Application entry point — agent-first, workflow-based navigation.

The sidebar is built from `pricing_agent.workflows.registry`, so navigation structure is
declared as data in one place rather than implied by filenames in a `pages/` directory.

Two things this shell is deliberately not:

* It does not route natural language. The assistant captures a question and says so.
* It does not orchestrate. Improve Aging Inventory describes its sequence rather than
  running it.

The three skills stay reusable capabilities underneath the workflows. None of them is a
top-level navigation entry.
"""

from __future__ import annotations

import streamlit as st

from pricing_agent.views import APP_TITLE, configure_page
from pricing_agent.workflows import pages as page_registry
from pricing_agent.workflows.registry import grouped

# The single page-configuration call for the whole application. With one entry script
# there is no longer a per-page call to compete with it.
configure_page(APP_TITLE)

# Build each page once, registering it by url_path so a view can link to a sibling with
# st.page_link — client-side navigation that preserves session state (the routed vehicle).
structure: dict[str, list] = {}
for group, definitions in grouped().items():
    built = []
    for definition in definitions:
        page = st.Page(
            definition.bound_render(),
            title=definition.navigation.title,
            url_path=definition.navigation.url_path,
            icon=definition.navigation.icon,
            default=definition.navigation.default,
        )
        page_registry.register(definition.navigation.url_path, page)
        built.append(page)
    structure[group.value] = built

navigation = st.navigation(structure)
navigation.run()
