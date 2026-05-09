# Remap-Key

A flexible, global key-to-text remapping tool for Windows, designed for productivity and automation. Remap hotkeys or scan codes to output text via direct typing or clipboard paste, with support for modifiers, exclusions, and clipboard restoration.

## Features

- **Multiple Output Modes**:
  - **Type Mode**: Directly types text using keyboard simulation.
  - **Clipboard Paste Mode**: Copies text to clipboard, pastes it, and optionally restores the previous clipboard content.
- **Flexible Triggers**:
  - Standard hotkeys (e.g., `f8`, `ctrl+shift+a`).
  - Scan codes for media keys or non-standard inputs.
  - Modifier support (ctrl, shift, alt, windows) and exclusions.
- **JSON-Driven Configuration**: Easily define multiple mappings in `remap-key.config.json`.
- **Clipboard Management**: Automatic restoration after paste operations to avoid disrupting workflow.
- **Event Capture**: Built-in tool to discover scan codes for unknown keys.
- **Boot Persistence**: PowerShell script to install as a scheduled task, running at logon.
- **Logging**: Configurable logging to console or file for debugging.
- **Cross-Platform Warnings**: Alerts for potential issues on Windows/Linux.

## Installation

1. **Clone or Download**: Place the repository in a desired location.
2. **Virtual Environment**: The repo includes a pre-configured venv (`python.venv-remap/`) with dependencies (`keyboard`, `pyperclip`).
   - Activate: `python.venv-remap\Scripts\activate`
   - Or install manually: `pip install keyboard pyperclip`
3. **Configuration**: Copy `remap-key.config.example.json` to `remap-key.config.json`, then edit it to define your mappings.
   - Example config is included so you can commit a clean sample file while keeping your local settings private.
4. **Install as Task** (for boot persistence):
   - Run `install-remap-task.ps1` as Administrator to create a scheduled task that starts at logon.
5. **Run Manually**: Execute `remap-key.py` or use `run-remap-key.cmd` / `run-remap-key-hidden.vbs` for hidden execution.

## Usage

### Basic Configuration

Edit `remap-key.config.json`:

```json
{
  "log_level": "INFO",
  "global": {
    "default_mode": "type",
    "default_paste_hotkey": "ctrl+v",
    "clipboard_settle_ms": 40,
    "clipboard_restore_delay_ms": 60,
    "typing_delay_seconds": 0.0
  },
  "mappings": [
    {
      "enabled": true,
      "trigger": "f8",
      "text": "Hello World!",
      "mode": "type",
      "suppress": false
    },
    {
      "enabled": true,
      "trigger": "f9",
      "text": "Pasted text",
      "mode": "clipboard_paste",
      "paste_hotkey": "ctrl+v",
      "suppress": false
    }
  ]
}
```

- **trigger**: Hotkey string or scan code (e.g., `"sc123"` for scan code 123).
- **mode**: `"type"` or `"clipboard_paste"`.
- **modifiers**: List of required modifiers (e.g., `["ctrl", "shift"]`).
- **exclude_if_modifiers**: Skip if these are pressed.
- **suppress**: Prevent the original key event.

### Running

- **Normal**: `python remap-key.py`
- **With Custom Config**: `python remap-key.py --config path/to/config.json`
- **Create Config Template**: `python remap-key.py --create-config`
- **Capture Events**: `python remap-key.py --capture-events 5` (to find scan codes)

### Task Management

- Use `remap-key-processes.ps1` to check or kill running instances.
- The task runs hidden via VBS/CMD scripts.

## Requirements

- Python 3.x
- Dependencies: `keyboard`, `pyperclip` (included in venv)
- Windows (primary support; Linux with caveats)
- Administrator rights for task installation

## Caveats

- May require elevated privileges on Windows for full functionality.
- Clipboard operations depend on `pyperclip`; ensure clipboard access.
- Experimental; test mappings carefully to avoid conflicts.

## License

MIT License - Intended for personal, non-commercial use. See LICENSE file for details.