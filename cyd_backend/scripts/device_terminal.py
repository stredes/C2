from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
import time
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[1]
APP = ROOT / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from server import BackendStore, load_config


HELP_TEXT = """\
Comandos locales:
  :help              muestra esta ayuda
  :ping              envia PING
  :status            envia GET_STATUS
  :ip                envia GET_IP
  :heap              envia GET_HEAP
  :device <id>       cambia el device_id
  :quit / exit       salir

Comandos al CYD:
  PING
  GET_STATUS
  GET_IP
  GET_HEAP
  ECHO hola
  cli <comando>      envia BRUCE_CLI <comando>

Comandos locales Windows:
  pc <comando>       ejecuta el comando en cmd.exe de este PC
"""


def read_json(path: pathlib.Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def find_result(results_file: pathlib.Path, command_id: str) -> dict[str, Any] | None:
    entries = read_json(results_file, [])
    if not isinstance(entries, list):
        return None
    for entry in reversed(entries):
        if isinstance(entry, dict) and entry.get("command_id") == command_id:
            return entry
    return None


def normalize_command(line: str) -> tuple[str | None, str | None]:
    raw = line.strip()
    if not raw:
        return None, None

    lower = raw.lower()
    aliases = {
        ":ping": "PING",
        ":status": "GET_STATUS",
        ":ip": "GET_IP",
        ":heap": "GET_HEAP",
    }
    if lower in aliases:
        return aliases[lower], None

    if lower.startswith("cli "):
        command = raw[4:].strip()
        if not command:
            return None, "Uso: cli <comando>"
        return f"BRUCE_CLI {command}", None

    return raw, None


def queue_and_wait(
    store: BackendStore,
    data_dir: pathlib.Path,
    device_id: str,
    command: str,
    timeout_seconds: float,
) -> int:
    payload = store.queue_command(device_id, command)
    command_id = payload["command_id"]
    print(f"-> {device_id} [{command_id}] {command}")

    deadline = time.monotonic() + timeout_seconds
    results_file = data_dir / "results" / f"{device_id}.json"
    while time.monotonic() < deadline:
        result = find_result(results_file, command_id)
        if result is not None:
            ok = bool(result.get("ok", False))
            status = "OK" if ok else "ERROR"
            output = str(result.get("output", ""))
            print(f"<- {status}: {output}")
            return 0 if ok else 2
        time.sleep(0.25)

    print(f"<- TIMEOUT: sin respuesta despues de {timeout_seconds:.0f}s")
    return 1


def run_local_cmd(command: str) -> int:
    if not command.strip():
        print("Uso: pc <comando>")
        return 2

    print(f"cmd.exe> {command}")
    try:
        completed = subprocess.run(
            ["cmd.exe", "/d", "/s", "/c", command],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        print(f"ERROR: {exc}")
        return 1

    if completed.stdout:
        print(completed.stdout.rstrip())
    if completed.stderr:
        print(completed.stderr.rstrip(), file=sys.stderr)
    print(f"[exit {completed.returncode}]")
    return completed.returncode


def interactive_shell(store: BackendStore, data_dir: pathlib.Path, device_id: str, timeout_seconds: float) -> int:
    print("Terminal CYD lista. Escribe :help para ayuda, :quit para salir.")
    print(f"Dispositivo activo: {device_id}")

    while True:
        try:
            line = input(f"cyd:{device_id}> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0

        if not line:
            continue

        lower = line.lower()
        if lower in {":quit", "quit", "exit"}:
            return 0
        if lower == ":help":
            print(HELP_TEXT)
            continue
        if lower.startswith(":device "):
            next_device = line.split(None, 1)[1].strip()
            if next_device:
                device_id = next_device
                print(f"Dispositivo activo: {device_id}")
            continue
        if lower.startswith("pc "):
            run_local_cmd(line[3:].strip())
            continue

        command, error = normalize_command(line)
        if error:
            print(error)
            continue
        if command is None:
            continue
        queue_and_wait(store, data_dir, device_id, command, timeout_seconds)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Interactive CYD command terminal")
    parser.add_argument("--config", default="config/backend.json", help="Path to backend config JSON")
    parser.add_argument("--device", default="cyd-2usb", help="Device ID")
    parser.add_argument("--command", help="Send one command and exit")
    parser.add_argument("--pc-command", help="Run one local command with cmd.exe and exit")
    parser.add_argument("--timeout", type=float, default=20.0, help="Seconds to wait for each result")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    config = load_config((ROOT / args.config).resolve())
    store = BackendStore(config.data_dir, config.device_stale_seconds)

    if args.pc_command:
        return run_local_cmd(args.pc_command)

    if args.command:
        command, error = normalize_command(args.command)
        if error:
            print(error)
            return 2
        if command is None:
            return 0
        return queue_and_wait(store, config.data_dir, args.device, command, args.timeout)

    return interactive_shell(store, config.data_dir, args.device, args.timeout)


if __name__ == "__main__":
    raise SystemExit(main())
