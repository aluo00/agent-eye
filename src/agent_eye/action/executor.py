"""
Action executor — translates parsed intents into PyAutoGUI calls.

All coordinates are validated against the agent's monitor before execution.
"""

from __future__ import annotations

import time
import sys

from ..config import monitor_bounds, in_bounds, PYAUTOGUI_FAILSAFE, STEP_DELAY

try:
    import pyautogui as _pg
except ImportError:
    print("agent-eye: pyautogui is required. Run: pip install pyautogui", file=sys.stderr)
    sys.exit(1)

try:
    import pyperclip as _clip
except ImportError:
    print("agent-eye: pyperclip is required. Run: pip install pyperclip", file=sys.stderr)
    sys.exit(1)


_pg.FAILSAFE = PYAUTOGUI_FAILSAFE


def _guard(x: int, y: int) -> None:
    """Raise if (x, y) is outside the agent's monitor."""
    if not in_bounds(x, y):
        b = monitor_bounds()
        raise ValueError(
            f"Coordinates ({x},{y}) are outside the agent monitor "
            f"[{b['left']}-{b['left']+b['width']}, {b['top']}-{b['top']+b['height']}]. "
            f"Refusing to operate on the wrong display."
        )


def click(x: int, y: int) -> str:
    """Left-click at absolute screen coordinates."""
    _guard(x, y)
    _pg.click(x, y)
    time.sleep(STEP_DELAY)
    return f"clicked ({x},{y})"


def double_click(x: int, y: int) -> str:
    """Double-click at absolute screen coordinates."""
    _guard(x, y)
    _pg.doubleClick(x, y)
    time.sleep(STEP_DELAY)
    return f"double-clicked ({x},{y})"


def right_click(x: int, y: int) -> str:
    """Right-click at absolute screen coordinates."""
    _guard(x, y)
    _pg.rightClick(x, y)
    time.sleep(STEP_DELAY)
    return f"right-clicked ({x},{y})"


def type_text(text: str) -> str:
    """Type text via clipboard paste (avoids keyboard layout issues)."""
    _clip.copy(text)
    _pg.hotkey("ctrl", "v")
    time.sleep(STEP_DELAY)
    preview = text if len(text) <= 60 else text[:57] + "..."
    return f"typed: {preview}"


def hotkey(keys: str) -> str:
    """Send a key combination like 'ctrl+s' or 'alt+tab'."""
    _pg.hotkey(*keys.split("+"))
    time.sleep(STEP_DELAY)
    return f"hotkey: {keys}"


def scroll(amount: int, x: int = 0, y: int = 0) -> str:
    """Scroll at position. Positive = up, negative = down."""
    if x or y:
        _guard(x, y)
        _pg.moveTo(x, y)
    _pg.scroll(amount)
    time.sleep(0.1)
    direction = "up" if amount > 0 else "down"
    return f"scrolled {direction} {abs(amount)} clicks"


def move_to(x: int, y: int) -> str:
    """Move the mouse to absolute screen coordinates (no click)."""
    _guard(x, y)
    _pg.moveTo(x, y)
    return f"moved to ({x},{y})"
