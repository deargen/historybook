"""History discovery — finds and imports *_histories.py and *.histories.py files."""

from __future__ import annotations

import hashlib
import importlib.util
import logging
import sys
import tomllib
from pathlib import Path

logger = logging.getLogger(__name__)

_MAIN_CONFIG_MODULE = "_historybook_main"


def find_pyproject(start: Path | None = None) -> Path | None:
    """Walk up from `start` (default cwd) to find pyproject.toml."""
    current = (start or Path.cwd()).resolve()
    for parent in [current, *current.parents]:
        candidate = parent / "pyproject.toml"
        if candidate.is_file():
            return candidate
    return None


def read_roots(pyproject_path: Path) -> list[str]:
    """Read [tool.historybook].roots from pyproject.toml.

    Warns if [tool.historybook] section is missing entirely.
    """
    with pyproject_path.open("rb") as f:
        data = tomllib.load(f)
    historybook_cfg = data.get("tool", {}).get("historybook")
    if historybook_cfg is None:
        logger.warning(
            '[tool.historybook] section not found in %s — defaulting roots to ["."]',
            pyproject_path,
        )
        return ["."]
    return historybook_cfg.get("roots", ["."])


def run_main_config(project_root: Path) -> None:
    """Run .historybook/main.py if it exists. Like Storybook's .storybook/main.ts.

    Skips execution if already run (e.g. by the parent process before spawning
    Streamlit), to avoid double-execution side effects.
    """
    if _MAIN_CONFIG_MODULE in sys.modules:
        return
    main_py = project_root / ".historybook" / "main.py"
    if not main_py.is_file():
        return
    logger.info("Running .historybook/main.py")
    _import_file(main_py, _MAIN_CONFIG_MODULE)


def discover_and_import(root: Path | None = None) -> int:
    """Discover *_histories.py and *.histories.py files and import them. Returns count of files imported."""
    pyproject_path = find_pyproject(root)
    if pyproject_path is None:
        logger.warning("No pyproject.toml found")
        return 0

    project_root = pyproject_path.parent

    # Run project-specific setup first (skips if already executed)
    run_main_config(project_root)

    roots = read_roots(pyproject_path)
    count = 0

    for history_root in roots:
        search_dir = project_root / history_root
        if not search_dir.is_dir():
            logger.warning("History root %s does not exist", search_dir)
            continue

        history_files = {
            *search_dir.rglob("*_histories.py"),
            *search_dir.rglob("*.histories.py"),
        }
        for history_file in sorted(history_files):
            _import_history_file(history_file)
            count += 1

    logger.info("Discovered %d history file(s)", count)
    return count


def _import_history_file(path: Path) -> None:
    """Import a single history file to trigger @component/@history decorators."""
    path_hash = hashlib.sha256(str(path.resolve()).encode()).hexdigest()[:12]
    safe_stem = path.stem.replace(".", "_")
    module_name = f"_historybook_history_{safe_stem}_{path_hash}"
    _import_file(path, module_name)


def _import_file(path: Path, module_name: str) -> None:
    """Import a Python file as a module with the given name."""
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        logger.warning("Could not load %s", path)
        return
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        logger.exception("Error loading history file %s", path)
