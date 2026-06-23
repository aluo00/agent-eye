"""
Screenshot capture for the agent's monitor.

Captures only the configured monitor, optionally resizes for API limits,
and returns base64-encoded PNG for multimodal model consumption.
"""

from __future__ import annotations

import base64
import io
import sys
from typing import Optional, Tuple

from PIL import Image

from ..config import agent_monitor_index

try:
    import mss as _mss
except ImportError:
    print("agent-eye: mss is required. Run: pip install mss", file=sys.stderr)
    sys.exit(1)

# Anthropic recommends max long edge 1568px for Claude; DeepSeek vision has
# similar limits. Client-side resize prevents server-side silent compression
# that shifts coordinates.
_MAX_LONG_EDGE = 1568


def capture(monitor_index: Optional[int] = None) -> Image.Image:
    """Capture the agent's monitor as a PIL Image (RGB)."""
    idx = monitor_index if monitor_index is not None else agent_monitor_index()
    with _mss.mss() as sct:
        monitor = sct.monitors[idx]
        raw = sct.grab(monitor)
        return Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")


def capture_base64(
    monitor_index: Optional[int] = None,
    max_long_edge: int = _MAX_LONG_EDGE,
) -> Tuple[str, int, int]:
    """
    Capture the agent's monitor and return (base64_png, width, height).

    The image is resized so its longer edge ≤ max_long_edge, then encoded as
    data-URL-suitable base64 (no prefix — the model caller adds that).
    """
    img = capture(monitor_index)
    w, h = img.size
    scale = min(max_long_edge / max(w, h), 1.0)
    if scale < 1.0:
        new_w, new_h = int(w * scale), int(h * scale)
        img = img.resize((new_w, new_h), Image.LANCZOS)
        w, h = new_w, new_h
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii"), w, h
