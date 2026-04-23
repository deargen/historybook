"""Reusable Mermaid-based pipeline diagram with live status animations.

Usage:
    from historybook.components import pipeline_diagram

    # Simple linear pipeline
    diagram = pipeline_diagram(
        steps=["Input", "Rotate", "X-Cut", "Y-Cut", "Output"],
        statuses={"Rotate": "running", "Input": "done"},
    )

    # Update during execution
    diagram.update({"Input": "done", "Rotate": "done", "X-Cut": "running"})

    # Complex DAG with parallel paths
    diagram = pipeline_diagram(
        edges=[
            ("Input", "Rotate"),
            ("Rotate", "X-Cut"),
            ("X-Cut", "Y-Cut Page 1"),
            ("X-Cut", "Y-Cut Page 2"),
            ("Y-Cut Page 1", "Grade"),
            ("Y-Cut Page 2", "Grade"),
        ],
        statuses={"Input": "done", "Rotate": "running"},
    )
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import streamlit as st
import streamlit.components.v1 as st_components

# Mermaid node ID must be alphanumeric + underscore only
_NON_ALNUM = re.compile(r"[^a-zA-Z0-9_]")


def _sanitize_id(name: str) -> str:
    return _NON_ALNUM.sub("_", name).strip("_") or "node"


def _build_mermaid(
    step_names: list[str],
    edges: list[tuple[str, str]],
    statuses: dict[str, str],
    icons: dict[str, str],
    direction: str,
) -> str:
    """Generate Mermaid flowchart code."""
    lines = [f"graph {direction}"]

    # Node definitions
    for name in step_names:
        sid = _sanitize_id(name)
        status = statuses.get(name, "waiting")
        icon = icons.get(name, "")
        label = f"{icon} {name}".strip() if icon else name

        if status == "done":
            label += " ✓"
        elif status == "error":
            label += " ✗"

        safe_label = (
            label.replace("\\", "\\\\").replace('"', "#quot;").replace("]", "#93;")
        )
        lines.append(f'    {sid}["{safe_label}"]')

    # Edges
    for src, dst in edges:
        src_id = _sanitize_id(src)
        dst_id = _sanitize_id(dst)
        src_status = statuses.get(src, "waiting")
        dst_status = statuses.get(dst, "waiting")

        if src_status == "done" and dst_status == "done":
            lines.append(f"    {src_id} ==> {dst_id}")
        else:
            lines.append(f"    {src_id} --> {dst_id}")

    # Style classes
    lines.append(
        "    classDef waiting fill:#f9fafb,stroke:#d1d5db,color:#9ca3af,stroke-width:1px"
    )
    lines.append(
        "    classDef running fill:#dbeafe,stroke:#2563eb,color:#1d4ed8,stroke-width:3px"
    )
    lines.append(
        "    classDef done fill:#d1fae5,stroke:#059669,color:#047857,stroke-width:2px"
    )
    lines.append(
        "    classDef error fill:#fee2e2,stroke:#dc2626,color:#991b1b,stroke-width:2px"
    )

    # Apply classes
    for name in step_names:
        sid = _sanitize_id(name)
        status = statuses.get(name, "waiting")
        lines.append(f"    class {sid} {status}")

    return "\n".join(lines)


def _compute_running_edge_ids(
    edges: list[tuple[str, str]],
    statuses: dict[str, str],
) -> list[str]:
    """Compute Mermaid edge IDs for edges leading to running nodes."""
    # Mermaid generates edge IDs as L_{src}_{dst}_{index}
    # For duplicate src->dst pairs, index increments. We assume index 0.
    result = []
    for src, dst in edges:
        if statuses.get(dst) == "running":
            src_id = _sanitize_id(src)
            dst_id = _sanitize_id(dst)
            result.append(f"L_{src_id}_{dst_id}_0")
    return result


def _render_html(
    mermaid_code: str,
    running_edge_ids: list[str],
    height: int,
) -> str:
    """Generate the full HTML with Mermaid + animations."""
    edge_ids_js = str(running_edge_ids)

    return f"""
    <script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
    <style>
        @keyframes pulse {{
            0%, 100% {{ opacity: 1; transform: scale(1); }}
            50% {{ opacity: 0.5; transform: scale(1.03); }}
        }}
        @keyframes dash {{
            to {{ stroke-dashoffset: -20; }}
        }}
        @keyframes glow {{
            0%, 100% {{ filter: drop-shadow(0 0 2px rgba(37,99,235,0.3)); }}
            50% {{ filter: drop-shadow(0 0 8px rgba(37,99,235,0.7)); }}
        }}
    </style>
    <div>
        <pre class="mermaid">
{mermaid_code}
        </pre>
    </div>
    <script>
        mermaid.initialize({{
            startOnLoad: false,
            theme: 'base',
            themeVariables: {{
                primaryColor: '#dbeafe',
                primaryTextColor: '#2563eb',
                primaryBorderColor: '#2563eb',
                lineColor: '#94a3b8',
                fontSize: '14px'
            }}
        }});
        mermaid.run().then(() => {{
            // Animate running nodes
            document.querySelectorAll('.running .basic.label-container').forEach(el => {{
                el.style.animation = 'glow 1.5s ease-in-out infinite';
            }});
            document.querySelectorAll('.running .nodeLabel').forEach(el => {{
                el.style.animation = 'pulse 1.5s ease-in-out infinite';
            }});
            // Animate edges leading to running nodes
            const runningEdges = {edge_ids_js};
            runningEdges.forEach(id => {{
                const el = document.getElementById(id);
                if (el) {{
                    el.setAttribute('stroke-dasharray', '8 4');
                    el.setAttribute('stroke-dashoffset', '0');
                    el.style.strokeDasharray = '8 4';
                    el.style.strokeDashoffset = '0';
                    el.style.animation = 'dash 0.6s linear infinite';
                    el.style.stroke = '#2563eb';
                    el.style.strokeWidth = '2.5';
                }}
            }});
        }});
    </script>
    """


@dataclass
class PipelineDiagram:
    """Handle for updating a pipeline diagram after creation."""

    _container: object
    _step_names: list[str]
    _edges: list[tuple[str, str]]
    _icons: dict[str, str]
    _direction: str
    _height: int
    _statuses: dict[str, str] = field(default_factory=dict)

    def update(self, statuses: dict[str, str]) -> None:
        """Re-render the diagram with new statuses."""
        self._statuses = statuses
        code = _build_mermaid(
            self._step_names, self._edges, statuses, self._icons, self._direction
        )
        edge_ids = _compute_running_edge_ids(self._edges, statuses)
        html = _render_html(code, edge_ids, self._height)
        self._container.empty()  # type: ignore[union-attr]
        with self._container.container():  # type: ignore[union-attr]
            st_components.html(html, height=self._height)


def pipeline_diagram(
    *,
    steps: list[str] | None = None,
    edges: list[tuple[str, str]] | None = None,
    statuses: dict[str, str] | None = None,
    icons: dict[str, str] | None = None,
    direction: str = "LR",
    height: int = 150,
) -> PipelineDiagram:
    """Create a pipeline flow diagram with live status updates.

    Args:
        steps: List of step names for a linear pipeline (auto-generates edges).
               Mutually exclusive with `edges` for defining structure.
        edges: List of (source, destination) tuples for complex DAGs.
               Step names are inferred from edges if `steps` is not provided.
        statuses: Dict mapping step name to status: "waiting", "running", "done", "error".
        icons: Dict mapping step name to emoji icon.
        direction: Mermaid direction: "LR" (left-right) or "TD" (top-down).
        height: Height of the diagram in pixels.

    Returns:
        PipelineDiagram handle with an `update()` method for live updates.
    """
    effective_statuses = statuses or {}
    effective_icons = icons or {}

    # Determine edges and step names
    if steps is not None and edges is not None:
        msg = "Provide either `steps` (linear) or `edges` (DAG), not both"
        raise ValueError(msg)

    if steps is not None:
        step_names = steps
        effective_edges = [(steps[i], steps[i + 1]) for i in range(len(steps) - 1)]
    elif edges is not None:
        effective_edges = edges
        # Infer step names preserving order
        seen: set[str] = set()
        step_names = []
        for src, dst in edges:
            for name in (src, dst):
                if name not in seen:
                    seen.add(name)
                    step_names.append(name)
    else:
        msg = "Provide either `steps` or `edges`"
        raise ValueError(msg)

    # Create container and render
    container = st.empty()
    diagram = PipelineDiagram(
        _container=container,
        _step_names=step_names,
        _edges=effective_edges,
        _icons=effective_icons,
        _direction=direction,
        _height=height,
        _statuses=effective_statuses,
    )
    diagram.update(effective_statuses)
    return diagram
