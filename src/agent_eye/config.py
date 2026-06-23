"""
Monitor and security configuration for agent-eye.

Reads AGENT_MONITOR from the environment to decide which display to operate on.
All coordinates are validated against this monitor's bounds before execution.
"""

import os
import sys
from typing import Optional

try:
    import mss as _mss
except ImportError:
    print("agent-eye: mss is required. Run: pip install mss", file=sys.stderr)
    sys.exit(1)


def _detect_monitors():
    """Return list of monitor dicts from mss."""
    with _mss.mss() as sct:
        return list(sct.monitors)


# --- lazy init ---
_monitors = None


def _get_monitors():
    global _monitors
    if _monitors is None:
        _monitors = _detect_monitors()
    return _monitors


def agent_monitor_index() -> int:
    """Which monitor index the agent should operate on (1 = primary, 2 = secondary)."""
    env = os.getenv("AGENT_MONITOR", "1").strip()
    try:
        idx = int(env)
    except ValueError:
        idx = 1
    monitors = _get_monitors()
    # monitors[0] = "all combined"; valid per-monitor indices start at 1
    if idx < 1 or idx >= len(monitors):
        print(
            f"agent-eye: AGENT_MONITOR={idx} out of range (1-{len(monitors)-1}), falling back to 1",
            file=sys.stderr,
        )
        idx = 1
    return idx


def monitor_bounds() -> dict:
    """
    Return the agent monitor's bounding box as:
        {"left": int, "top": int, "width": int, "height": int}
    """
    monitors = _get_monitors()
    idx = agent_monitor_index()
    m = monitors[idx]
    return {"left": m["left"], "top": m["top"], "width": m["width"], "height": m["height"]}


def in_bounds(x: int, y: int) -> bool:
    """Check whether absolute screen coordinates fall within the agent's monitor."""
    b = monitor_bounds()
    return b["left"] <= x <= b["left"] + b["width"] and b["top"] <= y <= b["top"] + b["height"]


# --- safety ---
PYAUTOGUI_FAILSAFE = True  # corner throw = emergency stop
REQUIRE_CONFIRMATION = os.getenv("AGENT_EYE_REQUIRE_CONFIRMATION", "").strip().lower() in (
    "1", "true", "yes",
)
STEP_DELAY = float(os.getenv("AGENT_EYE_STEP_DELAY", "0.5"))
