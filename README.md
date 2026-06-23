# agent-eye — Windows GUI automation MCP plugin for Reasonix

MCP stdio server that gives Reasonix eyes and hands on your Windows desktop.
It uses **Windows UI Automation** (fast, precise, free) as the primary perception
path, with screenshot capture as a fallback for custom-drawn UIs.

---

## Quick start (standalone .exe)

Pre-built: `dist/agent-eye.exe` (17 MB, self-contained, no Python required).

Configure in `reasonix.toml`:

```toml
[[plugins]]
name    = "agent-eye"
command = "D:\\Agent\\DeepSeek-Reasonix\\tools\\agent-eye\\dist\\agent-eye.exe"
env     = { AGENT_MONITOR = "1" }
```

The `AGENT_MONITOR` env var tells the plugin which display to control:
- `1` = primary monitor (default)
- `2` = secondary monitor

---

## Build from source

```powershell
cd tools\agent-eye
.\build.cmd                # one-shot: create venv, install deps, build .exe
```

Manual build:

```powershell
python -m venv venv
.\venv\Scripts\activate
pip install uiautomation pyautogui mss pyperclip pillow pyinstaller
python -m PyInstaller --onefile --console --name agent-eye --distpath .\dist --workpath .\build src\run.py
```

---

## Dev / pip install

During development, use pip install + venv python:

```toml
[[plugins]]
name    = "agent-eye"
command = "D:\\Agent\\DeepSeek-Reasonix\\tools\\agent-eye\\venv\\Scripts\\python.exe"
args    = ["-m", "agent_eye"]
env     = { AGENT_MONITOR = "1" }
```

---

## Tools

Reasonix surfaces these as `mcp__agent-eye__<name>`:

| Tool | Read-only | Description |
|---|---|---|
| `uia_get_elements` | ✅ | List interactive UI elements on the agent's monitor |
| `uia_click` | ❌ | Click an element by `[id=N]` |
| `uia_double_click` | ❌ | Double-click an element |
| `uia_right_click` | ❌ | Right-click an element |
| `uia_type_text` | ❌ | Type text (clipboard paste) |
| `uia_hotkey` | ❌ | Send keyboard shortcut (`ctrl+s`, `alt+tab`) |
| `uia_scroll` | ❌ | Scroll mouse wheel |
| `screenshot_capture` | ✅ | Capture agent monitor as PNG (for multimodal models) |

---

## Dependencies

- `uiautomation` — Windows UI Automation wrapper
- `pyautogui` — mouse/keyboard control
- `mss` — fast screen capture
- `pyperclip` — reliable text paste via clipboard
- `pillow` — image handling
