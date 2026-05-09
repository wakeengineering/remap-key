#!/usr/bin/env python3
"""Global key-to-text remapper process.

Features:
- Per-hotkey text output via direct typing or clipboard paste.
- Clipboard restoration after paste mode.
- JSON config file with multiple mappings.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import platform
import re
import sys
import threading
import time
from pathlib import Path
from typing import Any

try:
	import keyboard  # type: ignore
except ImportError as exc:
	raise SystemExit(
		"Missing dependency 'keyboard'. Install with: pip install keyboard"
	) from exc

try:
	import pyperclip  # type: ignore
except ImportError as exc:
	raise SystemExit(
		"Missing dependency 'pyperclip'. Install with: pip install pyperclip"
	) from exc


LOG = logging.getLogger("remap-key")

DEFAULT_CONFIG: dict[str, Any] = {
	"log_level": "INFO",
	"global": {
		"default_mode": "type",
		"default_paste_hotkey": "ctrl+v",
		"clipboard_settle_ms": 40,
		"clipboard_restore_delay_ms": 60,
		"typing_delay_seconds": 0.0,
	},
	"mappings": [
		{
			"enabled": True,
			"trigger": "f8",
			"text": "Hello from remap-key.py",
			"mode": "type",
			"suppress": False,
		},
		{
			"enabled": True,
			"trigger": "f9",
			"text": "Clipboard paste mode sample",
			"mode": "clipboard_paste",
			"paste_hotkey": "ctrl+v",
			"suppress": False,
		},
	],
}


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(
		description="Run a configurable key-to-text remapping process."
	)
	parser.add_argument(
		"--config",
		type=Path,
		default=Path(__file__).with_suffix(".config.json"),
		help="Path to JSON config file.",
	)
	parser.add_argument(
		"--create-config",
		action="store_true",
		help="Create or overwrite config template and exit.",
	)
	parser.add_argument(
		"--capture-events",
		type=int,
		default=0,
		help=(
			"Capture and print N raw key events, then exit. "
			"Useful to discover media key scan codes."
		),
	)
	parser.add_argument(
		"--log-file",
		type=Path,
		default=None,
		help="Optional path to append runtime logs.",
	)
	return parser.parse_args()


def write_config_template(config_path: Path, overwrite: bool = False) -> None:
	config_path.parent.mkdir(parents=True, exist_ok=True)
	if config_path.exists() and not overwrite:
		raise FileExistsError(f"Config already exists: {config_path}")
	config_path.write_text(json.dumps(DEFAULT_CONFIG, indent=2), encoding="utf-8")


def load_config(config_path: Path) -> dict[str, Any]:
	data = json.loads(config_path.read_text(encoding="utf-8"))
	if not isinstance(data, dict):
		raise ValueError("Config root must be a JSON object.")

	mappings = data.get("mappings")
	if not isinstance(mappings, list) or not mappings:
		raise ValueError("Config must contain a non-empty 'mappings' list.")

	for index, mapping in enumerate(mappings):
		if not isinstance(mapping, dict):
			raise ValueError(f"mappings[{index}] must be an object.")
		if "text" not in mapping:
			raise ValueError(f"mappings[{index}] must include 'text'.")

		has_trigger = "trigger" in mapping
		has_scancode = "trigger_scancode" in mapping
		if not has_trigger and not has_scancode:
			raise ValueError(
				f"mappings[{index}] must include 'trigger' or 'trigger_scancode'."
			)

		if has_trigger and (
			not isinstance(mapping["trigger"], str) or not mapping["trigger"].strip()
		):
			raise ValueError(f"mappings[{index}].trigger must be a non-empty string.")

		if has_scancode:
			sc = mapping["trigger_scancode"]
			valid_sc = isinstance(sc, int) and not isinstance(sc, bool) and sc != 0
			if not valid_sc and isinstance(sc, str):
				sc_str = sc.strip()
				if re.fullmatch(r"-?\d+", sc_str):
					valid_sc = int(sc_str) != 0
			if not valid_sc:
				raise ValueError(
					f"mappings[{index}].trigger_scancode must be a non-zero integer."
				)

		modifiers = mapping.get("modifiers", [])
		if modifiers is None:
			modifiers = []
		if not isinstance(modifiers, list):
			raise ValueError(f"mappings[{index}].modifiers must be a list of key names.")
		for mod_index, modifier in enumerate(modifiers):
			if not isinstance(modifier, str) or not modifier.strip():
				raise ValueError(
					f"mappings[{index}].modifiers[{mod_index}] must be a non-empty string."
				)

		excluded_modifiers = mapping.get("exclude_if_modifiers", [])
		if excluded_modifiers is None:
			excluded_modifiers = []
		if not isinstance(excluded_modifiers, list):
			raise ValueError(f"mappings[{index}].exclude_if_modifiers must be a list of key names.")
		for excl_index, modifier in enumerate(excluded_modifiers):
			if not isinstance(modifier, str) or not modifier.strip():
				raise ValueError(
					f"mappings[{index}].exclude_if_modifiers[{excl_index}] must be a non-empty string."
				)

		if not isinstance(mapping["text"], str):
			raise ValueError(f"mappings[{index}].text must be a string.")

	return data


def normalize_mode(mode: str) -> str:
	mode_map = {
		"type": "type",
		"typed": "type",
		"clipboard": "clipboard_paste",
		"paste": "clipboard_paste",
		"clipboard_paste": "clipboard_paste",
	}
	normalized = mode_map.get(mode.strip().lower())
	if normalized is None:
		raise ValueError(f"Unsupported mode: {mode}")
	return normalized


def running_with_admin_rights() -> bool:
	if platform.system() != "Windows":
		return False
	try:
		import ctypes

		return bool(ctypes.windll.shell32.IsUserAnAdmin())
	except Exception:
		return False


class RemapProcess:
	def __init__(self, config: dict[str, Any]) -> None:
		self.config = config
		self._lock = threading.Lock()
		self._hotkey_ids: list[Any] = []
		self._key_hooks: list[Any] = []

		global_cfg = config.get("global", {})
		if not isinstance(global_cfg, dict):
			global_cfg = {}

		self.default_mode = normalize_mode(str(global_cfg.get("default_mode", "type")))
		self.default_paste_hotkey = str(global_cfg.get("default_paste_hotkey", "ctrl+v"))
		self.clipboard_settle_seconds = (
			float(global_cfg.get("clipboard_settle_ms", 40)) / 1000.0
		)
		self.clipboard_restore_seconds = (
			float(global_cfg.get("clipboard_restore_delay_ms", 60)) / 1000.0
		)
		self.typing_delay_seconds = float(global_cfg.get("typing_delay_seconds", 0.0))

	def _parse_scancode(self, value: Any) -> int:
		if isinstance(value, bool):
			raise ValueError("Boolean is not a valid scan code.")
		if isinstance(value, int):
			sc = value
		elif isinstance(value, str) and re.fullmatch(r"-?\d+", value.strip()):
			sc = int(value.strip())
		else:
			raise ValueError(f"Invalid scan code value: {value}")
		if sc == 0:
			raise ValueError(f"Scan code must be non-zero: {value}")
		return sc

	def _normalize_modifiers(self, mapping: dict[str, Any]) -> list[str]:
		raw_modifiers = mapping.get("modifiers", [])
		if raw_modifiers is None:
			return []
		return [str(mod).strip().lower() for mod in raw_modifiers if str(mod).strip()]


	def _normalize_excluded_modifiers(self, mapping: dict[str, Any]) -> list[str]:
		raw_excluded = mapping.get("exclude_if_modifiers", [])
		if raw_excluded is None:
			return []
		return [str(mod).strip().lower() for mod in raw_excluded if str(mod).strip()]

	def _modifier_is_pressed(self, modifier: str) -> bool:
		alias_map = {
			"ctrl": ["ctrl", "left ctrl", "right ctrl"],
			"shift": ["shift", "left shift", "right shift"],
			"alt": ["alt", "left alt", "right alt"],
			"windows": ["windows", "left windows", "right windows"],
			"win": ["windows", "left windows", "right windows"],
		}
		candidates = alias_map.get(modifier, [modifier])
		for candidate in candidates:
			try:
				if keyboard.is_pressed(candidate):
					return True
			except Exception:
				continue
		return False

	def _modifiers_pressed(self, modifiers: list[str]) -> bool:
		for modifier in modifiers:
			if not self._modifier_is_pressed(modifier):
				return False
		return True

	def _resolve_trigger(self, mapping: dict[str, Any]) -> tuple[str, Any, str]:
		sc_value = mapping.get("trigger_scancode")
		if sc_value is not None:
			scan_code = self._parse_scancode(sc_value)
			return ("scancode", scan_code, f"sc{scan_code}")

		trigger = str(mapping["trigger"]).strip()
		match = re.fullmatch(r"sc(-?\d+)", trigger, flags=re.IGNORECASE)
		if match:
			scan_code = int(match.group(1))
			if scan_code == 0:
				raise ValueError("Scan code 0 is not supported.")
			return ("scancode", scan_code, f"sc{scan_code}")

		return ("hotkey", trigger, trigger)

	def _handle_scancode_event(
		self,
		event: Any,
		mapping: dict[str, Any],
		desired_event: str,
		required_modifiers: list[str] | None = None,
	) -> None:
		if getattr(event, "event_type", "") != desired_event:
			return
		if required_modifiers and not self._modifiers_pressed(required_modifiers):
			return
		excluded_modifiers = self._normalize_excluded_modifiers(mapping)
		if excluded_modifiers and self._modifiers_pressed(excluded_modifiers):
			return
		self.handle_mapping(mapping)

	def register_hotkeys(self) -> None:
		for mapping in self.config["mappings"]:
			enabled = bool(mapping.get("enabled", True))
			if not enabled:
				continue

			trigger_kind, trigger_value, trigger_label = self._resolve_trigger(mapping)
			required_modifiers = self._normalize_modifiers(mapping)
			excluded_modifiers = self._normalize_excluded_modifiers(mapping)
			suppress = bool(mapping.get("suppress", False))
			trigger_on_release = bool(mapping.get("trigger_on_release", False))
			effective_suppress = suppress

			# A scancode+modifier hook with suppress can swallow the base key event
			# before a non-modified mapping sees it.
			if trigger_kind == "scancode" and required_modifiers and suppress:
				LOG.warning(
					"For trigger '%s', suppress=true with modifiers may block other mappings; using suppress=false.",
					trigger_label,
				)
				effective_suppress = False

			registered_trigger = trigger_label
			if required_modifiers:
				registered_trigger = "+".join(required_modifiers + [trigger_label])

			if trigger_kind == "hotkey":
				hotkey_combo = str(trigger_value)
				if required_modifiers:
					hotkey_combo = "+".join(required_modifiers + [hotkey_combo])
				hotkey_id = keyboard.add_hotkey(
					hotkey_combo,
					lambda m=mapping: self._handle_mapping_with_exclusions(m),
					suppress=effective_suppress,
					trigger_on_release=trigger_on_release,
				)
				self._hotkey_ids.append(hotkey_id)
			else:
				# Register scancodes via keyboard's "scan code N" parser first.
				# This is usually more reliable for media keys on Windows.
				scan_hotkey = f"scan code {trigger_value}"
				if required_modifiers:
					scan_hotkey = "+".join(required_modifiers + [scan_hotkey])
				try:
					hotkey_id = keyboard.add_hotkey(
						scan_hotkey,
						lambda m=mapping: self._handle_mapping_with_exclusions(m),
							suppress=effective_suppress,
						trigger_on_release=trigger_on_release,
					)
					self._hotkey_ids.append(hotkey_id)
				except Exception:
					desired_event = "up" if trigger_on_release else "down"
					hook = keyboard.hook_key(
						trigger_value,
						lambda event, m=mapping, de=desired_event, mods=required_modifiers: self._handle_scancode_event(
							event, m, de, mods
						),
						suppress=effective_suppress,
					)
					self._key_hooks.append(hook)

			LOG.info(
				"Registered trigger '%s' (mode=%s)",
				registered_trigger,
				normalize_mode(str(mapping.get("mode", self.default_mode))),
			)

	def _handle_mapping_with_exclusions(self, mapping: dict[str, Any]) -> None:
		"""Wrapper that checks excluded_modifiers before calling handle_mapping."""
		excluded_modifiers = self._normalize_excluded_modifiers(mapping)
		if excluded_modifiers and self._modifiers_pressed(excluded_modifiers):
			return
		self.handle_mapping(mapping)

	def handle_mapping(self, mapping: dict[str, Any]) -> None:
		text = str(mapping["text"])
		mode = normalize_mode(str(mapping.get("mode", self.default_mode)))

		with self._lock:
			if mode == "type":
				delay = float(mapping.get("typing_delay_seconds", self.typing_delay_seconds))
				keyboard.write(text, delay=delay)
				return

			paste_hotkey = str(mapping.get("paste_hotkey", self.default_paste_hotkey))
			settle = float(mapping.get("clipboard_settle_ms", self.clipboard_settle_seconds * 1000.0)) / 1000.0
			restore_delay = (
				float(
					mapping.get(
						"clipboard_restore_delay_ms",
						self.clipboard_restore_seconds * 1000.0,
					)
				)
				/ 1000.0
			)
			self._emit_via_clipboard(text=text, paste_hotkey=paste_hotkey, settle=settle, restore_delay=restore_delay)

	def _emit_via_clipboard(
		self,
		text: str,
		paste_hotkey: str,
		settle: float,
		restore_delay: float,
	) -> None:
		previous_clipboard = None
		can_restore = False

		try:
			previous_clipboard = pyperclip.paste()
			can_restore = True
		except pyperclip.PyperclipException:
			LOG.warning("Could not read clipboard before paste; restore will be skipped.")

		pyperclip.copy(text)
		time.sleep(max(0.0, settle))
		keyboard.send(paste_hotkey)

		if can_restore:
			time.sleep(max(0.0, restore_delay))
			pyperclip.copy(previous_clipboard)

	def run(self) -> None:
		self.register_hotkeys()
		LOG.info("Remap process started. Press Ctrl+C to stop.")
		keyboard.wait()


def configure_logging(level_name: str, log_file: Path | None = None) -> None:
	level = getattr(logging, level_name.upper(), logging.INFO)
	formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

	handlers: list[logging.Handler] = []
	stream_handler = logging.StreamHandler()
	stream_handler.setFormatter(formatter)
	handlers.append(stream_handler)

	if log_file is not None:
		log_file.parent.mkdir(parents=True, exist_ok=True)
		file_handler = logging.FileHandler(log_file, encoding="utf-8")
		file_handler.setFormatter(formatter)
		handlers.append(file_handler)

	root_logger = logging.getLogger()
	root_logger.handlers.clear()
	root_logger.setLevel(level)
	for handler in handlers:
		root_logger.addHandler(handler)


def log_platform_warnings() -> None:
	system = platform.system()
	if system == "Linux":
		if hasattr(os, "geteuid") and os.geteuid() != 0:
			LOG.warning(
				"Linux global key hooks often require elevated privileges or input device access."
			)
		if os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland":
			LOG.warning(
				"Wayland sessions may block global key capture/injection for security reasons."
			)
	elif system == "Windows":
		if not running_with_admin_rights():
			LOG.warning(
				"On Windows, remaps may not work in elevated apps unless this script also runs elevated."
			)


def main() -> int:
	args = parse_args()

	if args.capture_events > 0:
		print("Capturing key events. Press the target key(s)...")
		for index in range(args.capture_events):
			event = keyboard.read_event(suppress=False)
			print(
				f"{index + 1}: type={getattr(event, 'event_type', '?')} "
				f"scan_code={getattr(event, 'scan_code', '?')} "
				f"name={getattr(event, 'name', '?')}"
			)
		return 0

	if args.create_config:
		write_config_template(args.config, overwrite=True)
		print(f"Wrote config template: {args.config}")
		return 0

	if not args.config.exists():
		write_config_template(args.config, overwrite=False)
		print(
			"No config file found. Created template at "
			f"{args.config}. Edit it and re-run."
		)
		return 0

	try:
		config = load_config(args.config)
	except (ValueError, json.JSONDecodeError) as exc:
		print(f"Invalid config: {exc}", file=sys.stderr)
		return 2

	configure_logging(str(config.get("log_level", "INFO")), args.log_file)
	log_platform_warnings()

	try:
		remapper = RemapProcess(config)
		remapper.run()
		return 0
	except KeyboardInterrupt:
		LOG.info("Stopping remap process.")
		return 0
	except Exception as exc:
		LOG.exception("Fatal error: %s", exc)
		return 1


if __name__ == "__main__":
	raise SystemExit(main())
