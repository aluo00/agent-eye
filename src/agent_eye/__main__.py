"""
Entry point for `python -m agent_eye`.

Starts the MCP stdio JSON-RPC server. All application logs go to stderr;
stdout is reserved for the JSON-RPC protocol.
"""

from __future__ import annotations

import sys

from .config import agent_monitor_index, monitor_bounds, PYAUTOGUI_FAILSAFE, STEP_DELAY
from .server import serve


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
