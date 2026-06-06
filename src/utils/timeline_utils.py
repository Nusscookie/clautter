"""Shared timeline naming utility — avoids name collisions across modules."""

from __future__ import annotations
from typing import Any


def _unique_timeline_name(project: Any, base_name: str) -> str:
    """Return a name that does not collide with existing timelines."""
    try:
        count = project.GetTimelineCount()
        existing = {
            project.GetTimelineByIndex(i + 1).GetName()
            for i in range(count)
        }
    except Exception:
        existing = set()

    name = base_name
    i = 2
    while name in existing:
        name = f"{base_name}_{i}"
        i += 1
    return name
