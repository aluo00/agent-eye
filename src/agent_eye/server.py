"""
MCP stdio JSON-RPC 2.0 server for agent-eye.

Speaks the same wire protocol as the reasonix-plugin-example reference:
newline-delimited JSON-RPC 2.0 on stdin/stdout (logs → stderr).

Implements: initialize, tools/list, tools/call.
Does NOT implement prompts or resources (tool-only server).
"""

from __future__ import annotations

import json
import re as _re
import sys
import time as _time
from typing import Any

from .config import monitor_bounds
from .perception import uia, screenshot as _ss
from .action import executor as _exec

# --- MCP constants ---
PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "agent-eye"
# Version is set at build time; keep in sync with pyproject.toml.
SERVER_VERSION = "0.1.0"

# JSON-RPC error codes.
CODE_METHOD_NOT_FOUND = -32601
CODE_INVALID_PARAMS = -32602


# ============================================================
#  Tool definitions
# ============================================================

_TOOLS: list[dict[str, Any]] = [
    {
        "name": "uia_get_elements",
        "description": (
            "Get all interactive UI elements from the currently focused window on "
            "the agent's monitor. Returns a numbered list with element IDs, control "
            "types (Button/Edit/ComboBox/etc.), labels, bounding rectangles, and "
            "enabled state. Use this FIRST for any GUI task — it gives precise "
            "coordinates that UIA can click without needing a screenshot."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "max_elements": {
                    "type": "integer",
                    "description": "Maximum elements to return (default 80, max 120).",
                    "default": 80,
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "title": "Get UI elements",
        },
    },
    {
        "name": "uia_click",
        "description": (
            "Click an interactive element by its [id=N] from uia_get_elements. "
            "Only operates on the agent's monitor — coordinates are validated."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "element_id": {
                    "type": "integer",
                    "description": "The [id=N] of the element from uia_get_elements.",
                },
            },
            "required": ["element_id"],
        },
        "annotations": {
            "readOnlyHint": False,
            "title": "Click element",
        },
    },
    {
        "name": "uia_double_click",
        "description": "Double-click an element by its [id=N] from uia_get_elements.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "element_id": {
                    "type": "integer",
                    "description": "The [id=N] of the element from uia_get_elements.",
                },
            },
            "required": ["element_id"],
        },
        "annotations": {
            "readOnlyHint": False,
            "title": "Double-click element",
        },
    },
    {
        "name": "uia_right_click",
        "description": "Right-click an element by its [id=N] from uia_get_elements.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "element_id": {
                    "type": "integer",
                    "description": "The [id=N] of the element from uia_get_elements.",
                },
            },
            "required": ["element_id"],
        },
        "annotations": {
            "readOnlyHint": False,
            "title": "Right-click element",
        },
    },
    {
        "name": "uia_type_text",
        "description": (
            "Type text. To type into a specific field, call uia_click first to "
            "focus it, then call uia_type_text. Uses clipboard paste to avoid "
            "keyboard layout issues."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The text to type.",
                },
            },
            "required": ["text"],
        },
        "annotations": {
            "readOnlyHint": False,
            "title": "Type text",
        },
    },
    {
        "name": "uia_hotkey",
        "description": (
            "Send a keyboard shortcut. Examples: 'ctrl+s', 'ctrl+c', 'alt+tab', "
            "'win+e', 'ctrl+shift+esc'. Keys are pressed together, then released."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "keys": {
                    "type": "string",
                    "description": "Key combination joined by '+' (e.g. 'ctrl+s').",
                },
            },
            "required": ["keys"],
        },
        "annotations": {
            "readOnlyHint": False,
            "title": "Send hotkey",
        },
    },
    {
        "name": "uia_scroll",
        "description": (
            "Scroll the mouse wheel. Positive = up, negative = down. "
            "Optionally specify an element_id to move to that element first."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "amount": {
                    "type": "integer",
                    "description": "Scroll amount (positive=up, negative=down).",
                },
                "element_id": {
                    "type": "integer",
                    "description": "Optional [id=N] to move to before scrolling.",
                },
            },
            "required": ["amount"],
        },
        "annotations": {
            "readOnlyHint": False,
            "title": "Scroll",
        },
    },
    {
        "name": "screenshot_capture",
        "description": (
            "Capture the agent's monitor as a base64-encoded PNG. Use this when "
            "uia_get_elements returns few/no results (custom-drawn UIs, games, "
            "Unity Scene view) and you need visual context. The image is resized "
            "to fit within 1568px on the longest edge to stay under API limits."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
        "annotations": {
            "readOnlyHint": True,
            "title": "Capture screenshot",
        },
    },
]


# ============================================================
#  Tool handlers
# ============================================================

# Cache the last uia_get_elements result so click/scroll can resolve IDs.
_last_elements: list[dict[str, Any]] = []
_last_elements_time: float = 0.0  # timestamp of last fetch
_ELEMENT_STALE_SEC = 5.0  # warn if elements older than this

# Circuit breaker: track consecutive failures across tool calls.
_failure_count: int = 0
_CIRCUIT_BREAKER_MAX_FAILURES = 5
_CIRCUIT_BREAKER_TIMEOUT_SEC = 30.0
_first_failure_time: float = 0.0


def _check_circuit_breaker() -> None:
    """Raise if too many consecutive failures have occurred."""
    global _failure_count, _first_failure_time
    if _failure_count >= _CIRCUIT_BREAKER_MAX_FAILURES:
        elapsed = _time.time() - _first_failure_time
        if elapsed < _CIRCUIT_BREAKER_TIMEOUT_SEC:
            raise RuntimeError(
                f"Circuit breaker: {_failure_count} consecutive failures in "
                f"{elapsed:.0f}s. Refusing further actions for "
                f"{_CIRCUIT_BREAKER_TIMEOUT_SEC - elapsed:.0f}s. "
                f"Call uia_get_elements to reset."
            )
        # Timeout expired — reset.
        _reset_circuit_breaker()


def _reset_circuit_breaker() -> None:
    global _failure_count, _first_failure_time
    _failure_count = 0
    _first_failure_time = 0.0


def _record_failure() -> None:
    global _failure_count, _first_failure_time
    if _failure_count == 0:
        _first_failure_time = _time.time()
    _failure_count += 1


def _record_success() -> None:
    _reset_circuit_breaker()


# Prompt injection patterns — detect attempts to override agent instructions.
_INJECTION_PATTERNS: list[tuple[str, str]] = [
    (r"(?i)ignore\s+(previous|all|your|above|the)\s+.*\s*instructions?", "instruction override"),
    (r"(?i)jailbreak", "jailbreak keyword"),
    (r"(?i)you\s+are\s+now\s+(a\s+)?DAN", "DAN mode"),
    (r"(?i)system\s*prompt\s*:", "system prompt injection"),
    (r"(?i)forget\s+everything", "context reset attempt"),
    (r"\{\{.*?\}\}", "template injection"),
    (r"\{\%.*?\%\}", "template tag injection"),
    (r"(?i)<script[^>]*>", "script tag"),
]


def _sanitize_text(text: str) -> tuple[str, list[str]]:
    """Check text for injection patterns. Returns (sanitized_text, warnings)."""
    warnings: list[str] = []
    for pattern, desc in _INJECTION_PATTERNS:
        if _re.search(pattern, text):
            warnings.append(f"detected {desc} in input; text may be unsafe")
    return text, warnings


def _handle_uia_get_elements(args: dict[str, Any]) -> str:
    global _last_elements, _last_elements_time
    max_el = min(int(args.get("max_elements", 80)), 120)
    elements = uia.get_elements(max_elements=max_el)
    _last_elements = elements
    _last_elements_time = _time.time()
    _reset_circuit_breaker()  # fresh perception resets circuit
    text = uia.flatten_for_llm(elements)
    mb = monitor_bounds()
    header = (
        f"Monitor [{mb['left']},{mb['top']} {mb['width']}x{mb['height']}]: "
        f"{len(elements)} interactive elements\n\n"
    )
    return header + text


def _resolve_and_verify(args: dict[str, Any]) -> dict[str, Any]:
    """
    Look up an element by ID AND verify coordinates are still valid.
    
    Fresh-fetches elements if the cache is stale, then checks that the
    resolved element's bounding box hasn't shifted significantly.
    Raises ValueError on mismatch (stale element → LLM should re-fetch).
    """
    eid = int(args.get("element_id", -1))
    
    # Stale cache? Re-fetch.
    if _last_elements_time == 0 or (_time.time() - _last_elements_time) > _ELEMENT_STALE_SEC:
        _ = _handle_uia_get_elements({})
    
    if eid < 0 or eid >= len(_last_elements):
        raise ValueError(
            f"Element [id={eid}] not found. "
            f"Call uia_get_elements first, then use a valid id (0-{len(_last_elements)-1})."
        )
    
    cached = _last_elements[eid]
    
    # Coordinate verification: do a quick fresh UIA scan and look for a
    # matching element near the cached position (within 20px tolerance).
    # This catches cases where the UI shifted between perception and action.
    fresh = uia.get_elements(max_elements=120)
    cx, cy = uia.element_center(cached)
    verified = False
    for f in fresh:
        fx, fy = uia.element_center(f)
        if abs(fx - cx) <= 20 and abs(fy - cy) <= 20:
            # Same position → element still there.
            if f["control_type"] == cached["control_type"]:
                verified = True
                break
            # Different type but same position (e.g. overlay) → warn but proceed.
            verified = True
            break
    
    if not verified:
        raise ValueError(
            f"Element [id={eid}] ({cached['control_type']}) at ({cx},{cy}) "
            f"no longer found on screen. The UI may have changed. "
            f"Call uia_get_elements to refresh the element list."
        )
    
    return cached


def _handle_click(args: dict[str, Any]) -> str:
    _check_circuit_breaker()
    try:
        el = _resolve_and_verify(args)
        cx, cy = uia.element_center(el)
        label = el["name"] or el["automation_id"] or f"({el['control_type']})"
        result = _exec.click(cx, cy)
        _record_success()
        return f"{result} — {el['control_type']} \"{label}\" [verified @ ({cx},{cy})]"
    except Exception:
        _record_failure()
        raise


def _handle_double_click(args: dict[str, Any]) -> str:
    _check_circuit_breaker()
    try:
        el = _resolve_and_verify(args)
        cx, cy = uia.element_center(el)
        label = el["name"] or el["automation_id"] or f"({el['control_type']})"
        result = _exec.double_click(cx, cy)
        _record_success()
        return f"{result} — {el['control_type']} \"{label}\" [verified]"
    except Exception:
        _record_failure()
        raise


def _handle_right_click(args: dict[str, Any]) -> str:
    _check_circuit_breaker()
    try:
        el = _resolve_and_verify(args)
        cx, cy = uia.element_center(el)
        label = el["name"] or el["automation_id"] or f"({el['control_type']})"
        result = _exec.right_click(cx, cy)
        _record_success()
        return f"{result} — {el['control_type']} \"{label}\" [verified]"
    except Exception:
        _record_failure()
        raise


def _handle_type_text(args: dict[str, Any]) -> str:
    text = str(args.get("text", ""))
    if not text:
        raise ValueError("text must be a non-empty string")
    # Injection check.
    sanitized, warnings = _sanitize_text(text)
    result = _exec.type_text(sanitized)
    if warnings:
        result += " | WARNING: " + "; ".join(warnings)
    return result


def _handle_hotkey(args: dict[str, Any]) -> str:
    keys = str(args.get("keys", ""))
    if not keys:
        raise ValueError("keys must be a non-empty string like 'ctrl+s'")
    return _exec.hotkey(keys)


def _handle_scroll(args: dict[str, Any]) -> str:
    amount = int(args.get("amount", 0))
    if amount == 0:
        raise ValueError("amount must be non-zero")
    eid = args.get("element_id")
    if eid is not None:
        el = _resolve_and_verify(args)
        cx, cy = uia.element_center(el)
    else:
        cx, cy = 0, 0
    return _exec.scroll(amount, cx, cy)


def _handle_screenshot(args: dict[str, Any]) -> dict[str, Any]:
    b64, w, h = _ss.capture_base64()
    mb = monitor_bounds()
    desc = (
        f"Screenshot captured: {w}x{h} px "
        f"(original monitor {mb['width']}x{mb['height']})"
    )
    return _image_result(b64, desc)


_TOOL_HANDLERS: dict[str, Any] = {
    "uia_get_elements": _handle_uia_get_elements,
    "uia_click": _handle_click,
    "uia_double_click": _handle_double_click,
    "uia_right_click": _handle_right_click,
    "uia_type_text": _handle_type_text,
    "uia_hotkey": _handle_hotkey,
    "uia_scroll": _handle_scroll,
    "screenshot_capture": _handle_screenshot,
}


# ============================================================
#  JSON-RPC server
# ============================================================


def _text_result(text: str, is_error: bool = False) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": text}],
        "isError": is_error,
    }


def _image_result(b64: str, description: str = "") -> dict[str, Any]:
    """Build a tool result containing an image and its description."""
    content: list[dict[str, Any]] = [
        {"type": "image", "data": b64, "mimeType": "image/png"},
    ]
    if description:
        content.insert(0, {"type": "text", "text": description})
    return {"content": content, "isError": False}


def handle_request(req: dict[str, Any]) -> dict[str, Any] | None:
    """Process one JSON-RPC request. Returns a response dict, or None for notifications."""
    req_id = req.get("id")
    method = req.get("method", "")

    # Notifications (no id) — silently ignore.
    if req_id is None:
        return None

    resp: dict[str, Any] = {"jsonrpc": "2.0", "id": req_id}

    try:
        if method == "initialize":
            resp["result"] = {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {
                    "tools": {},
                    # No prompts, no resources — tool-only server.
                },
                "serverInfo": {
                    "name": SERVER_NAME,
                    "version": SERVER_VERSION,
                },
            }

        elif method == "tools/list":
            resp["result"] = {"tools": _TOOLS}

        elif method == "tools/call":
            params = req.get("params", {})
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})

            handler = _TOOL_HANDLERS.get(tool_name)
            if handler is None:
                resp["error"] = {
                    "code": CODE_INVALID_PARAMS,
                    "message": f"unknown tool: {tool_name}",
                }
            else:
                try:
                    result = handler(arguments)
                    # Handler may return a str (→ text result) or a dict (→ already formatted).
                    if isinstance(result, str):
                        resp["result"] = _text_result(result, False)
                    else:
                        resp["result"] = result
                except Exception as exc:
                    # Handler errors become isError content results so the model
                    # can read the message and adapt.
                    resp["result"] = _text_result(str(exc), True)

        # prompts/list and resources/list — not implemented.
        # We MUST return an empty list rather than an error so Reasonix doesn't
        # fail the startup discover phase. The capabilities block already
        # signals we don't have them, but some clients probe anyway.
        elif method == "prompts/list":
            resp["result"] = {"prompts": []}
        elif method == "resources/list":
            resp["result"] = {"resources": []}

        else:
            resp["error"] = {
                "code": CODE_METHOD_NOT_FOUND,
                "message": f"method not found: {method}",
            }

    except Exception as exc:
        resp["error"] = {
            "code": CODE_INVALID_PARAMS,
            "message": str(exc),
        }

    return resp


def serve() -> None:
    """
    Run the read-dispatch-reply loop on stdin/stdout.

    Stdin carries newline-delimited JSON-RPC requests.
    Stdout carries the responses, one JSON object per line.
    Stderr carries logs (forwarded by Reasonix to the terminal).
    """
    # Windows: force UTF-8 on stdio to avoid GBK encoding errors.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            print(f"agent-eye: skipping unparseable line: {line[:120]}", file=sys.stderr)
            continue

        resp = handle_request(req)
        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()
