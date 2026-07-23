"""A runtime lookup from `url_path` to the live `st.Page` object.

`st.page_link` and `st.switch_page` navigate **client-side**, preserving Streamlit session
state — a raw HTML anchor does a full page reload and wipes it. To link to a workflow from
inside a view (the assistant's "open the full analysis" button), that view needs the actual
`st.Page` object, which only exists once `app.py` has built the navigation.

`app.py` registers each page here as it builds them, before `navigation.run()` renders the
current page, so any view can look up a sibling page by its `url_path`.

This module holds no Streamlit call of its own — just a dict — so importing it is free and
cycle-free.
"""

from __future__ import annotations

from typing import Any

_PAGES: dict[str, Any] = {}


def register(url_path: str, page: Any) -> None:
    _PAGES[url_path] = page


def page_for(url_path: str) -> Any | None:
    return _PAGES.get(url_path)


def clear() -> None:
    """Only for tests — the live app registers once per process."""
    _PAGES.clear()
