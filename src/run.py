"""
PyInstaller entry point for agent-eye.

This file is the argument to PyInstaller. It uses absolute imports so the
frozen executable can find the package. Equivalent to `python -m agent_eye`.
"""

import sys
import os

# Ensure the src directory is on sys.path so absolute imports work.
_src = os.path.dirname(os.path.abspath(__file__))
if _src not in sys.path:
    sys.path.insert(0, _src)

from agent_eye.config import agent_monitor_index, monitor_bounds, PYAUTOGUI_FAILSAFE, STEP_DELAY
from agent_eye.server import serve


def main() -> None:
    mb = monitor_bounds()
    print(
        f"agent-eye v0.1.0 — controlling monitor {agent_monitor_index()} "
        f"[{mb['left']},{mb['top']} {mb['width']}x{mb['height']}]",
        file=sys.stderr,
    )
    print(
        f"AGENT_MONITOR={agent_monitor_index()}  "
        f"FAILSAFE={'ON' if PYAUTOGUI_FAILSAFE else 'OFF'}  "
        f"STEP_DELAY={STEP_DELAY}s",
        file=sys.stderr,
    )
    serve()


if __name__ == "__main__":
    main()
