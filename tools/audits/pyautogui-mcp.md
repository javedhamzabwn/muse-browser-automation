# Source-Code Analysis Report: PyAutoGUI MCP (`pyautogui-mcp`)

- **Repository**: https://github.com/chigwell/pyautogui-mcp
- **Commit**: `3f22e0153d9cce878ffb74cd515b239048a63b1b`
- **Language**: Python
- **License**: Custom Open Source
- **Architecture**: Python PyAutoGUI wrapper exposing MCP JSON-RPC protocol
- **Decision**: **COMPATIBLE**

## Architecture & Process Model
- **Process Model**: Python subprocess executing pywin32 / ctypes
- **Communication**: stdio (MCP protocol)
- **MCP Implementation**: Yes (stdio)
- **Native Components**: None (Pure Script / Managed)
- **Platforms**: windows, linux, darwin

## Strengths & Capabilities
- [+] Pure Python coordinate mouse clicking
- [+] Keyboard typing and hotkey dispatch
- [+] Pillow screenshot capture

## Limitations & Security Concerns
- [-] No direct UI Automation accessibility tree inspection
- [-] Screenshot capture slower than Direct3D / Rust
- [!] Security: Global mouse and keyboard input control

## Key Source Files
- `main.py`
- `pyautogui_mcp\app.py`
- `pyautogui_mcp\__init__.py`
- `pyautogui_mcp\__main__.py`

## Integration Options
1. Direct in-process Python module import
2. Subprocess stdio MCP bridge

**Recommended Integration**: In-process Python adapter or stdio MCP bridge
