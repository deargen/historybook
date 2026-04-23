"""Streamlit app — Historybook UI with sac.menu sidebar."""

from __future__ import annotations

import fnmatch
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import streamlit as st
import streamlit_antd_components as sac

from historybook.discovery import (
    discover_and_import,
    get_history_root_dirs,
)
from historybook.registry import clear_registry, get_all_components

if TYPE_CHECKING:
    from historybook.registry import ComponentEntry, HistoryEntry

logger = logging.getLogger(__name__)


# ── Helpers ──


def _filter_by_search(
    components: list[ComponentEntry], search: str
) -> list[ComponentEntry]:
    """Filter components/histories by search text."""
    if not search:
        return components
    search_lower = search.lower()
    return [
        c
        for c in components
        if search_lower in c.name.lower()
        or any(search_lower in s.name.lower() for s in c.histories)
    ]


def _group_by_tags(
    components: list[ComponentEntry],
) -> dict[str, list[ComponentEntry]]:
    """Group components by tag. A component with multiple tags appears in each."""
    groups: dict[str, list[ComponentEntry]] = {}
    for c in components:
        if not c.tags:
            groups.setdefault("other", []).append(c)
        else:
            for tag in c.tags:
                groups.setdefault(tag, []).append(c)
    return groups


def _make_key(comp: ComponentEntry, history: HistoryEntry) -> str:
    return f"{comp.name}::{history.name}"


# ── Build sac.menu items ──


def _build_menu_items(
    components: list[ComponentEntry],
) -> tuple[list[sac.MenuItem], dict[str, tuple[ComponentEntry, HistoryEntry]]]:
    """Build sac.MenuItem tree grouped by tags.

    Returns:
        (menu_items, lookup) where lookup maps history label to (component, history).
    """
    tag_groups = _group_by_tags(components)
    items: list[sac.MenuItem] = []
    lookup: dict[str, tuple[ComponentEntry, HistoryEntry]] = {}

    for tag, tag_components in sorted(tag_groups.items()):
        tag_children: list[sac.MenuItem] = []

        for comp in tag_components:
            history_children: list[sac.MenuItem] = []
            for s in comp.histories:
                key = _make_key(comp, s)
                # Use unique key as label to avoid duplicates across components
                history_children.append(sac.MenuItem(key, icon="bookmark"))
                lookup[key] = (comp, s)

            tag_children.append(
                sac.MenuItem(comp.name, icon="box", children=history_children)
            )

        items.append(sac.MenuItem(tag.upper(), icon="tag", children=tag_children))

    return items, lookup


def _find_key_by_menu_path(
    components: list[ComponentEntry],
    comp_name: str,
    history_name: str,
) -> tuple[ComponentEntry, HistoryEntry] | None:
    """Find component+history by names selected from the menu."""
    for c in components:
        if c.name == comp_name:
            for s in c.histories:
                if s.name == history_name:
                    return c, s
    return None


# ── Sidebar ──


def _render_sidebar(
    components: list[ComponentEntry],
) -> tuple[HistoryEntry | None, ComponentEntry | None]:
    """Render sidebar with search + sac.menu."""
    with st.sidebar:
        st.markdown("## 📖 Historybook")

        # Search
        search = st.text_input(
            "🔍 Search",
            key="history_search",
            placeholder="Type to filter...",
            label_visibility="collapsed",
        )

        st.divider()

        filtered = _filter_by_search(components, search)

        if not filtered:
            st.caption("No histories match the search.")
            return None, None

        menu_items, lookup = _build_menu_items(filtered)

        selected_label = sac.menu(
            items=menu_items,
            key="historybook_menu",
            open_all=True,
            indent=20,
            format_func=lambda x: x.split("::")[-1] if "::" in x else x,
        )

        # sac.menu returns the unique key (comp::history)
        if selected_label and selected_label in lookup:
            comp, s = lookup[selected_label]
            return s, comp

        # Default to first history
        if filtered and filtered[0].histories:
            return filtered[0].histories[0], filtered[0]

        return None, None


@st.fragment
def _render_history(entry: HistoryEntry) -> None:
    """Render a history in the main content area.

    Wrapped in @st.fragment so interactions inside the history (buttons, inputs)
    only rerun this fragment, not the whole page (including the sidebar menu).
    """
    try:
        entry.fn()
    except Exception:
        logger.exception("Error rendering history %s", entry.name)
        st.error(f"Error rendering history: {entry.name}")


# ── File watchers for auto-reload ──


@st.cache_resource
def _register_history_watchers(root_dirs_key: tuple[str, ...]) -> bool:
    """Register Streamlit file watchers on history root dirs so edits/additions auto-rerun.

    Runs once per Streamlit server process (via @st.cache_resource), regardless of
    how many sessions open the app. The `root_dirs_key` tuple is only used as the
    cache key — changing `[tool.historybook].roots` triggers re-registration.
    """
    try:
        from streamlit.runtime import get_instance
        from streamlit.watcher.path_watcher import watch_dir
    except ImportError:
        logger.warning(
            "Streamlit watcher API unavailable; history auto-reload disabled"
        )
        return False

    def _on_change(changed_path: str) -> None:
        name = Path(changed_path).name
        if not (
            fnmatch.fnmatch(name, "*_histories.py")
            or fnmatch.fnmatch(name, "*.histories.py")
        ):
            return
        # Drop the stale module so the next rerun re-execs fresh source.
        for mod_name in list(sys.modules.keys()):
            mod = sys.modules.get(mod_name)
            if mod is not None and getattr(mod, "__file__", None) == changed_path:
                del sys.modules[mod_name]
        # Ask every active session to rerun.
        try:
            runtime = get_instance()
            for session_info in runtime._session_mgr.list_active_sessions():
                session_info.session.request_rerun(None)
        except Exception:
            logger.exception("Failed to trigger historybook rerun")

    for root_str in root_dirs_key:
        try:
            watch_dir(root_str, _on_change)
        except Exception:
            logger.exception("Failed to watch %s", root_str)

    return True


# ── Launch ──


def launch(root: Path | None = None) -> None:
    """Discover histories and render the Streamlit app."""
    # Patch asyncio to allow nested event loops (histories call async LLM APIs
    # from sync Streamlit callbacks via asyncio.run())
    import nest_asyncio

    nest_asyncio.apply()

    st.set_page_config(
        page_title="Historybook",
        page_icon="📖",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    clear_registry()
    discover_and_import(root)
    components = get_all_components()

    _register_history_watchers(tuple(str(d) for d in get_history_root_dirs(root)))

    if not components:
        st.error(
            "No histories found. Check [tool.historybook] roots in pyproject.toml."
        )
        return

    selected_history, _ = _render_sidebar(components)

    if selected_history:
        _render_history(selected_history)
    else:
        st.info("Select a history from the sidebar.")


# Streamlit runs this file directly — parse args and launch
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=None)
    args, _ = parser.parse_known_args()
    launch(root=args.root)
