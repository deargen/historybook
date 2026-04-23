# Historybook: Storybook-like inspection for Python pipelines

[![image](https://img.shields.io/pypi/v/historybook.svg)](https://pypi.python.org/pypi/historybook)
[![PyPI - Downloads](https://img.shields.io/pypi/dm/historybook)](https://pypistats.org/packages/historybook)
[![image](https://img.shields.io/pypi/l/historybook.svg)](https://pypi.python.org/pypi/historybook)
[![image](https://img.shields.io/pypi/pyversions/historybook.svg)](https://pypi.python.org/pypi/historybook)

**Storybook for Python.** Inspect every pipeline in your project on a single
page.

Historybook is a thin Streamlit app that walks your repo, finds all history
files, and aggregates them behind a searchable sidebar menu. Each "history" is
just a function you decorate — when the user picks it from the menu,
Historybook runs the function and renders whatever Streamlit output it
produces.

## Why

Visual testing for **backend** pipelines without spinning up an API server and
a JS frontend. If you just want to poke at a pipeline — step through stages,
swap inputs, see intermediate outputs — a full web stack is overkill. Write a
function, decorate it, run `historybook`.

Good fits:

- Step-by-step visualisation of multi-stage pipelines (OCR, ETL, ML inference,
  data cleaning).
- Inspecting intermediate artefacts (images, DataFrames, JSON) during
  development.
- **LLM / agent output inspection.** Calls are expensive, outputs are
  open-ended, and assertion-style unit tests don't catch things like "the
  explanation is technically correct but phrased weirdly." Historybook gives
  you a quick human-in-the-loop surface: render the prompt, response,
  tool-calls, token/cost metrics side-by-side and eyeball quality across
  prompt/model variants.
- Demoing internal tools to teammates without deploying anything.

## Install

```bash
pip install historybook          # or: uv add --dev historybook
```

Historybook is a development tool, so prefer `uv add --dev` (or `pip install`
into a dev-only env) — there's no reason to ship it as a runtime dependency.

## Quick start

**1.** Add `[tool.historybook]` to your `pyproject.toml`:

```toml
[tool.historybook]
roots = ["."]                    # directories to scan (relative to pyproject.toml)

[tool.historybook.theme]
primaryColor = "#2563eb"         # optional
```

**2.** Write a history file. Any file matching `*_histories.py` or
`*.histories.py` anywhere under `roots` is auto-discovered.

```python
# src/myproject/ocr.histories.py
import streamlit as st
from historybook import component, history

@component("OCR Pipeline", tags=["ocr"])
class OcrPipeline:
    @history("Single Page")
    def single_page(self):
        st.image("samples/page1.png")
        st.json({"confidence": 0.97, "lang": "en"})

    @history("Multi Page")
    def multi_page(self):
        for i in range(3):
            st.image(f"samples/page{i}.png")
```

**3.** Launch the app from anywhere inside the repo:

```bash
historybook
```

A Streamlit page opens with a sidebar grouped by tag → component → history.
Type in the search box to filter; click any history to run it in the main
pane.

## Discovery rules

- Historybook walks up from the cwd to find `pyproject.toml`, then scans each
  directory listed in `[tool.historybook].roots`.
- It `rglob`s for **`*_histories.py`** and **`*.histories.py`**.
- Optional per-project setup lives in `.historybook/main.py` (like Storybook's
  `.storybook/main.ts`). It runs once in the parent process before Streamlit
  starts — good for setting env vars that Streamlit must inherit.

## Pipeline diagram component

Historybook ships with a Mermaid-based pipeline diagram helper with live
status updates — useful for visualising DAGs while they execute.

```python
import streamlit as st
from historybook import component, history
from historybook.components import pipeline_diagram

@component("Document Pipeline", tags=["ocr"])
class DocPipeline:
    @history("Linear flow")
    def linear(self):
        diagram = pipeline_diagram(
            steps=["Input", "Rotate", "X-Cut", "Y-Cut", "Output"],
            statuses={"Input": "done", "Rotate": "running"},
        )
        if st.button("Next step"):
            diagram.update({"Input": "done", "Rotate": "done", "X-Cut": "running"})

    @history("DAG with parallel paths")
    def dag(self):
        pipeline_diagram(
            edges=[
                ("Input", "Rotate"),
                ("Rotate", "X-Cut"),
                ("X-Cut", "Y-Cut Page 1"),
                ("X-Cut", "Y-Cut Page 2"),
                ("Y-Cut Page 1", "Grade"),
                ("Y-Cut Page 2", "Grade"),
            ],
            statuses={"Input": "done", "Rotate": "running"},
            icons={"Input": "📄", "Grade": "🎯"},
            direction="LR",      # or "TD"
        )
```

Statuses: `"waiting"` (default), `"running"` (pulsing blue), `"done"` (green
with ✓), `"error"` (red with ✗). Running edges get an animated dashed
stroke. Call `diagram.update(new_statuses)` to re-render in place.

## Excluding history files from other tools

History files are executed by Historybook, not imported by your app — so
they're usually noise for linters, type checkers, test runners, and package
builds. Suggested `pyproject.toml` snippets:

```toml
# pytest — skip collection (including --doctest-modules)
[tool.pytest.ini_options]
addopts = "--ignore-glob=**/*_histories.py --ignore-glob=**/*.histories.py"

# pyright / basedpyright — skip type checking
[tool.pyright]
ignore = ["**/*_histories.py", "**/*.histories.py"]

# ruff — skip linting
[tool.ruff]
extend-exclude = ["**/*_histories.py", "**/*.histories.py"]

# hatchling — don't ship history files in the wheel/sdist
[tool.hatch.build]
exclude = ["**/*_histories.py", "**/*.histories.py"]
```

Notes:

- **pytest**: `--ignore-glob` is the canonical escape hatch; for finer
  control, use `collect_ignore_glob` in a `conftest.py`.
- **pyright**: prefer `ignore` over `exclude` — `exclude` replaces pyright's
  default exclude list (`node_modules`, `__pycache__`, etc.), `ignore` adds to
  it.
- **ruff**: `extend-exclude` preserves ruff's defaults (`.git`, `.venv`, …);
  plain `exclude` replaces them.
- **hatchling**: patterns are gitignore-style. If you set `packages`/`include`
  explicitly, also exclude there.

## API reference

```python
from historybook import component, history
```

- **`@component(name: str, *, tags: list[str] | None = None)`** — class
  decorator. Registers the class as a component grouped under the given tag(s)
  in the sidebar.
- **`@history(name: str)`** — method decorator. Marks a method on a
  `@component` class as a selectable history. The method takes `self` only and
  renders with Streamlit calls.

```python
from historybook.components import pipeline_diagram
```

- **`pipeline_diagram(*, steps=..., edges=..., statuses=..., icons=..., direction="LR", height=150)`**
  — Mermaid flowchart. Pass `steps` (linear) **or** `edges` (DAG), not both.
  Returns a `PipelineDiagram` with an `update(statuses)` method.

## CLI

```bash
historybook                      # run from anywhere inside the repo
historybook --root path/to/dir   # override the scan root
```
