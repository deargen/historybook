from historybook.registry import component, history

from ._version import get_version_dict

__version__ = get_version_dict()["version"]


__all__ = ["component", "history", "run"]

_DEFAULT_PRIMARY_COLOR = "#2563eb"


def _run_main_config() -> None:
    """
    Run .historybook/main.py before launching Streamlit.

    This runs in the parent process so env vars like DYLD_FALLBACK_LIBRARY_PATH
    are inherited by the Streamlit child process.
    """
    from historybook.discovery import find_pyproject, run_main_config

    pyproject = find_pyproject()
    if not pyproject:
        return
    run_main_config(pyproject.parent)


def _read_theme_color() -> str:
    """Read theme.primaryColor from [tool.historybook] in pyproject.toml."""
    import tomllib

    from historybook.discovery import find_pyproject

    pyproject = find_pyproject()
    if not pyproject:
        return _DEFAULT_PRIMARY_COLOR
    with pyproject.open("rb") as f:
        data = tomllib.load(f)
    return (
        data.get("tool", {})
        .get("historybook", {})
        .get("theme", {})
        .get("primaryColor", _DEFAULT_PRIMARY_COLOR)
    )


def run() -> None:
    """CLI entry point — launches Streamlit app."""
    import os
    import subprocess
    import sys
    from pathlib import Path

    # Run project config before launching Streamlit so env vars are inherited
    _run_main_config()

    app_path = Path(__file__).parent / "app.py"
    primary_color = _read_theme_color()

    # Forward --root argument to Streamlit
    args = sys.argv[1:]
    root_arg = None
    for i, arg in enumerate(args):
        if arg == "--root" and i + 1 < len(args):
            root_arg = args[i + 1]

    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(app_path),
        "--theme.primaryColor",
        primary_color,
        "--",
    ]
    if root_arg:
        cmd.extend(["--root", root_arg])

    proc = subprocess.run(cmd, check=False, env=os.environ)
    sys.exit(proc.returncode)
