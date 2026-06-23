"""
Windows UI Automation perception layer.

Walks the UIA accessibility tree of the foreground window, filters elements
to the agent's monitor, and formats them as an LLM-friendly numbered list.
"""

from __future__ import annotations

import math
import sys
from typing import Any, Optional

from ..config import monitor_bounds, in_bounds

try:
    import uiautomation as _auto
except ImportError:
    print("agent-eye: uiautomation is required. Run: pip install uiautomation", file=sys.stderr)
    sys.exit(1)


# Depth cap to avoid infinite recursion into huge trees.
_MAX_DEPTH = 20

# Priority order for sorting: lower = more interesting to the agent.
_PRIORITY: dict[str, int] = {
    "Button": 0,
    "Edit": 1,
    "ComboBox": 1,
    "MenuItem": 2,
    "Hyperlink": 2,
    "TabItem": 2,
    "ListItem": 3,
    "TreeItem": 3,
    "CheckBox": 2,
    "RadioButton": 2,
    "Slider": 3,
    "Spinner": 3,
}

# Control types that are rarely useful to the agent — skip them.
_SKIP_TYPES: set[str] = {
    "Text",      # usually static labels, not interactive
    "Image",
    "Group",
    "Pane",
    "ToolBar",   # the bar itself; its buttons are already listed
    "ScrollBar",
    "Thumb",
    "Header",
    "HeaderItem",
    "Separator",
}


def get_elements(
    max_elements: int = 80,
    monitor_bounds_override: Optional[dict] = None,
) -> list[dict[str, Any]]:
    """
    Walk the UIA tree of the foreground window and return interactive elements
    that fall within the agent's monitor.

    Returns a list of dicts with keys:
        control_type, name, automation_id, class_name,
        x, y, w, h, enabled, is_keyboard_focusable
    """
    bounds = monitor_bounds_override or monitor_bounds()
    try:
        window = _auto.GetForegroundControl()
    except Exception:
        return []

    elements: list[dict[str, Any]] = []

    def walk(control, depth: int = 0):
        if depth > _MAX_DEPTH or len(elements) >= max_elements * 2:
            return
        try:
            rect = control.BoundingRectangle
            if not rect or rect[2] <= rect[0] or rect[3] <= rect[1]:
                # Degenerate rect; still walk children.
                pass
            else:
                x, y = rect[0], rect[1]
                w, h = rect[2] - rect[0], rect[3] - rect[1]

                # Filter: only elements on the agent's monitor.
                if in_bounds(x, y):
                    ct = control.ControlTypeName or ""
                    if ct not in _SKIP_TYPES and w * h > 4:  # skip invisible/tiny
                        info = {
                            "control_type": ct,
                            "name": control.Name or "",
                            "automation_id": control.AutomationId or "",
                            "x": x, "y": y, "w": w, "h": h,
                            "enabled": bool(control.IsEnabled),
                            "is_keyboard_focusable": bool(control.IsKeyboardFocusable),
                        }
                        elements.append(info)
        except Exception:
            pass

        try:
            children = control.GetChildren()
        except Exception:
            return
        for child in children:
            walk(child, depth + 1)

    walk(window)

    # Sort by priority, then dedupe / trim.
    elements.sort(key=lambda e: _PRIORITY.get(e["control_type"], 5))
    elements = elements[:max_elements]

    return elements


def flatten_for_llm(
    elements: list[dict[str, Any]],
) -> str:
    """
    Format elements into a text block the LLM can reason about.

    Example output:
        [id=0] Button "Save" (1400,820)~(1480,850)
        [id=1] Edit "File name:" (1200,780)~(1400,810)
    """
    if not elements:
        return "(no interactive elements found on the agent monitor — the window may be empty, custom-drawn, or on the other display)"

    lines: list[str] = []
    for i, el in enumerate(elements):
        label = el["name"] or el["automation_id"] or f"({el['control_type']})"
        state = ""
        if not el["enabled"]:
            state = " [disabled]"
        lines.append(
            f"[id={i}] {el['control_type']} \"{label}\" "
            f"({el['x']},{el['y']})~({el['x'] + el['w']},{el['y'] + el['h']})"
            f"{state}"
        )
    return "\n".join(lines)


def element_center(element: dict[str, Any]) -> tuple[int, int]:
    """Return the absolute screen (x, y) of an element's center."""
    return (
        element["x"] + element["w"] // 2,
        element["y"] + element["h"] // 2,
    )
