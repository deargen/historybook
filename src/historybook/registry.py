"""History registry — collects and organizes component/history hierarchy."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


_components: list[ComponentEntry] = []


@dataclass
class HistoryEntry:
    """A single history (configuration) within a component."""

    name: str
    fn: Callable[[], None]


@dataclass
class ComponentEntry:
    """A component with tags and multiple histories."""

    name: str
    tags: list[str]
    histories: list[HistoryEntry] = field(default_factory=list)
    module_path: str = ""


def history(name: str):
    """Decorator to register a history method within a @component class.

    Usage:
        @component("X-Cutting", tags=["x-cut"])
        class ColumnDetection:
            @history("Single Page")
            def single_page(self):
                st.image(...)
    """

    def decorator(fn: Callable[..., None]) -> Callable[..., None]:
        fn._history_name = name  # type: ignore[attr-defined]
        return fn

    return decorator


def component(name: str, *, tags: list[str] | None = None):
    """Decorator to register a component class containing @history methods.

    Usage:
        @component("X-Cutting", tags=["x-cut"])
        class ColumnDetection:
            @history("Single Page")
            def single_page(self):
                ...
    """

    def decorator[T](cls: type[T]) -> type[T]:
        instance = cls()
        histories: list[HistoryEntry] = []

        for attr_name in dir(cls):
            attr = getattr(cls, attr_name)
            if callable(attr) and hasattr(attr, "_history_name"):
                # Bind the method to the instance
                bound_method = getattr(instance, attr_name)
                histories.append(HistoryEntry(name=attr._history_name, fn=bound_method))

        _components.append(
            ComponentEntry(
                name=name,
                tags=tags or [],
                histories=histories,
                module_path=cls.__module__,
            )
        )
        return cls

    return decorator


def get_all_components() -> list[ComponentEntry]:
    return list(_components)


def clear_registry() -> None:
    _components.clear()
