from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from server import BackendStore, load_config

CLIENT_CONFIG = ROOT.parent / "cyd_http_client" / "src" / "config.h"


@dataclass(slots=True)
class RuntimeState:
    log_lines: int = 10
    message: str = "Listo"
    last_refresh: str = "-"


class BackendProcessManager:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.process: subprocess.Popen[str] | None = None

    def start(self) -> str:
        if self.running:
            return "El backend ya esta iniciado"
        command = [sys.executable, str(self.root / "scripts" / "run_backend.py")]
        self.process = subprocess.Popen(
            command,
            cwd=self.root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        time.sleep(1.0)
        if self.running:
            return f"Backend iniciado con PID {self.process.pid}"
        return "No se pudo iniciar el backend"

    def stop(self) -> str:
        if not self.running:
            return "El backend no esta corriendo"
        assert self.process is not None
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)
        pid = self.process.pid
        self.process = None
        return f"Backend detenido (PID {pid})"

    @property
    def running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    @property
    def pid(self) -> int | None:
        if self.running and self.process is not None:
            return self.process.pid
        return None


def clear_screen() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def read_last_lines(path: Path, max_lines: int) -> list[str]:
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    return lines[-max_lines:]


def request_json(url: str, headers: dict[str, str] | None = None) -> tuple[bool, int | None, dict[str, Any]]:
    request = Request(url, headers=headers or {})
    try:
        with urlopen(request, timeout=2.5) as response:
            payload = response.read().decode("utf-8")
            return True, response.status, json.loads(payload)
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            payload = {"error": body}
        return False, exc.code, payload
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        return False, None, {"error": str(exc)}


def detect_serial_ports() -> list[dict[str, str]]:
    try:
        from serial.tools import list_ports  # type: ignore

        ports = []
        for port in list_ports.comports():
            ports.append(
                {
                    "device": port.device,
                    "description": port.description or "-",
                    "hwid": port.hwid or "-",
                    "status": "ok",
                }
            )
        return ports
    except Exception:
        pass

    if os.name != "nt":
        return []

    command = (
        "Get-CimInstance Win32_SerialPort | "
        "Select-Object DeviceID,Description,Status | ConvertTo-Json -Compress"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0 or not result.stdout.strip():
        return []

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []

    if isinstance(payload, dict):
        payload = [payload]

    ports = []
    for item in payload:
        ports.append(
            {
                "device": str(item.get("DeviceID", "-")),
                "description": str(item.get("Description", "-")),
                "hwid": "-",
                "status": str(item.get("Status", "-")),
            }
        )
    return ports


def parse_client_config(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    patterns = {
        "SERVER_HOST": r'SERVER_HOST\s*=\s*"([^"]+)"',
        "SERVER_PORT": r"SERVER_PORT\s*=\s*(\d+)",
        "DEVICE_ID": r'DEVICE_ID\s*=\s*"([^"]+)"',
        "WIFI_SSID": r'WIFI_SSID\s*=\s*"([^"]+)"',
    }
    result: dict[str, str] = {}
    for key, pattern in patterns.items():
        match = re.search(pattern, text)
        result[key] = match.group(1) if match else "-"
    return result


def update_backend_config(config_path: Path, field: str, value: str | int) -> None:
    payload = read_json(config_path, {})
    payload[field] = value
    config_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def update_client_define(path: Path, define_name: str, value: str) -> bool:
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    if define_name == "SERVER_HOST":
        pattern = r'(SERVER_HOST\s*=\s*")[^"]+(";)'
        replacement = rf'\g<1>{value}\2'
    elif define_name == "SERVER_PORT":
        pattern = r"(SERVER_PORT\s*=\s*)\d+(;)"
        replacement = rf"\g<1>{value}\2"
    else:
        return False
    updated, count = re.subn(pattern, replacement, text)
    if count == 0:
        return False
    path.write_text(updated, encoding="utf-8")
    return True


def prompt_line(prompt: str) -> str:
    print()
    return input(prompt).strip()


def render_line(width: int) -> str:
    return "+" + ("-" * (width - 2)) + "+"


def truncate(text: str, width: int) -> str:
    if len(text) <= width:
        return text
    if width <= 3:
        return text[:width]
    return text[: width - 3] + "..."


def boxed_line(width: int, text: str = "") -> str:
    body = truncate(text, width - 4)
    return "| " + body.ljust(width - 4) + " |"


def format_device_rows(devices: dict[str, Any]) -> list[str]:
    rows = []
    if not devices:
        return ["Sin dispositivos registrados"]
    for device_id, device in sorted(devices.items()):
        status = device.get("derived_status", device.get("status", "unknown"))
        ip = device.get("ip") or "-"
        age = str(device.get("age_seconds", "-"))
        fw = device.get("firmware") or "-"
        rows.append(f"{device_id} | {status} | ip={ip} | age={age}s | fw={fw}")
    return rows


def format_command_rows(commands_dir: Path) -> list[str]:
    rows = []
    for file in sorted(commands_dir.glob("*.json")):
        queue = read_json(file, [])
        for command in queue[-3:]:
            rows.append(f"{file.stem} | {command.get('command_id')} | {command.get('command')}")
    return rows or ["Sin comandos en cola"]


def format_result_rows(results_dir: Path) -> list[str]:
    rows = []
    for file in sorted(results_dir.glob("*.json")):
        results = read_json(file, [])
        for result in results[-2:]:
            output = str(result.get("output", ""))
            rows.append(
                f"{file.stem} | ok={result.get('ok')} | cmd={result.get('command_id')} | {truncate(output, 80)}"
            )
    return rows[-6:] or ["Sin resultados recientes"]


def collect_dashboard(config_path: Path, manager: BackendProcessManager) -> dict[str, Any]:
    config = load_config(config_path)
    headers = {
        "X-Token-Id": config.token_id,
        "X-Secret-Key": config.secret_key,
    }
    base_url = f"http://127.0.0.1:{config.port}"
    health_ok, health_code, health_payload = request_json(f"{base_url}/health")
    status_ok, status_code, status_payload = request_json(f"{base_url}/api/v1/status", headers=headers)
    state = status_payload.get("state", {}) if status_ok else {}
    serial_ports = detect_serial_ports()
    client_cfg = parse_client_config(CLIENT_CONFIG)
    log_lines = read_last_lines(config.log_file, 10)
    return {
        "config": config,
        "base_url": base_url,
        "health_ok": health_ok,
        "health_code": health_code,
        "health_payload": health_payload,
        "status_ok": status_ok,
        "status_code": status_code,
        "state": state,
        "serial_ports": serial_ports,
        "client_cfg": client_cfg,
        "log_lines": log_lines,
        "backend_pid": manager.pid,
    }


def render_dashboard(data: dict[str, Any], runtime: RuntimeState) -> None:
    width = 108
    config = data["config"]
    summary = data["state"].get("summary", {})
    devices = data["state"].get("devices", {})
    serial_ports = data["serial_ports"]
    client_cfg = data["client_cfg"]
    device_rows = format_device_rows(devices)
    command_rows = format_command_rows(config.data_dir / "commands")
    result_rows = format_result_rows(config.data_dir / "results")
    log_rows = data["log_lines"][-runtime.log_lines :] or ["Sin logs todavia"]

    lines = [
        render_line(width),
        boxed_line(width, "CYD SERVER MONITOR :: ASCII OPS PANEL"),
        boxed_line(
            width,
            f"backend={config.host}:{config.port} pid={data['backend_pid'] or '-'} health={'UP' if data['health_ok'] else 'DOWN'}"
            f" status_api={'UP' if data['status_ok'] else 'DOWN'} refresh={runtime.last_refresh}",
        ),
        boxed_line(
            width,
            f"firmware_target={client_cfg.get('SERVER_HOST')}:{client_cfg.get('SERVER_PORT')} device_id={client_cfg.get('DEVICE_ID')}"
        ),
        boxed_line(
            width,
            f"devices={summary.get('device_count', 0)} online={summary.get('online_count', 0)}"
            f" stale={summary.get('stale_count', 0)} offline={summary.get('offline_count', 0)}"
            f" serial_ports={len(serial_ports)}",
        ),
        render_line(width),
        boxed_line(width, "DISPOSITIVOS"),
    ]
    for row in device_rows[:6]:
        lines.append(boxed_line(width, row))
    lines.append(render_line(width))
    lines.append(boxed_line(width, "PUERTOS SERIE DETECTADOS"))
    if serial_ports:
        for port in serial_ports[:4]:
            lines.append(
                boxed_line(width, f"{port['device']} | {port['status']} | {port['description']} | {port['hwid']}")
            )
    else:
        lines.append(boxed_line(width, "No se detectaron puertos serie"))
    lines.append(render_line(width))
    lines.append(boxed_line(width, "COLA Y RESULTADOS"))
    for row in command_rows[:3]:
        lines.append(boxed_line(width, f"QUEUE  {row}"))
    for row in result_rows[:3]:
        lines.append(boxed_line(width, f"RESULT {row}"))
    lines.append(render_line(width))
    lines.append(boxed_line(width, "LOGS EN VIVO"))
    for row in log_rows:
        lines.append(boxed_line(width, row))
    lines.append(render_line(width))
    lines.append(
        boxed_line(
            width,
            "teclas: [s] start [x] stop [p] backend port [h] backend host [P] client port [H] client host [c] queue [l] more logs [k] less logs [q] quit",
        )
    )
    lines.append(boxed_line(width, f"mensaje: {runtime.message}"))
    lines.append(render_line(width))
    print("\n".join(lines))


def queue_command(config_path: Path, device_id: str, command: str) -> str:
    config = load_config(config_path)
    store = BackendStore(config.data_dir)
    payload = store.queue_command(device_id, command)
    return f"Comando encolado: {payload['command_id']} -> {device_id} :: {command}"


def main() -> None:
    config_path = (ROOT / "config" / "backend.json").resolve()
    manager = BackendProcessManager(ROOT)
    runtime = RuntimeState()

    if os.name != "nt":
        print("Esta TUI fue optimizada para Windows/PowerShell, pero puede correr igual.")

    while True:
        data = collect_dashboard(config_path, manager)
        runtime.last_refresh = time.strftime("%Y-%m-%d %H:%M:%S")
        clear_screen()
        render_dashboard(data, runtime)

        if os.name != "nt":
            command = prompt_line("Comando (s/x/p/h/P/H/c/l/k/q, Enter=refresh): ")
        else:
            import msvcrt

            command = ""
            start_wait = time.time()
            while time.time() - start_wait < 1.0:
                if msvcrt.kbhit():
                    command = msvcrt.getwch()
                    break
                time.sleep(0.1)

        if not command:
            continue

        if command == "q":
            if manager.running:
                manager.stop()
            break
        if command == "s":
            runtime.message = manager.start()
            continue
        if command == "x":
            runtime.message = manager.stop()
            continue
        if command == "l":
            runtime.log_lines = min(runtime.log_lines + 5, 30)
            runtime.message = f"Logs visibles: {runtime.log_lines}"
            continue
        if command == "k":
            runtime.log_lines = max(runtime.log_lines - 5, 5)
            runtime.message = f"Logs visibles: {runtime.log_lines}"
            continue
        if command == "p":
            value = prompt_line("Nuevo backend port: ")
            if value.isdigit():
                update_backend_config(config_path, "port", int(value))
                runtime.message = f"Puerto backend actualizado a {value}"
            else:
                runtime.message = "Puerto invalido"
            continue
        if command == "h":
            value = prompt_line("Nuevo backend host: ")
            if value:
                update_backend_config(config_path, "host", value)
                runtime.message = f"Host backend actualizado a {value}"
            else:
                runtime.message = "Host invalido"
            continue
        if command == "P":
            value = prompt_line("Nuevo SERVER_PORT del cliente CYD: ")
            if value.isdigit() and update_client_define(CLIENT_CONFIG, "SERVER_PORT", value):
                runtime.message = f"SERVER_PORT del cliente actualizado a {value}"
            else:
                runtime.message = "No se pudo actualizar SERVER_PORT"
            continue
        if command == "H":
            value = prompt_line("Nuevo SERVER_HOST del cliente CYD: ")
            if value and update_client_define(CLIENT_CONFIG, "SERVER_HOST", value):
                runtime.message = f"SERVER_HOST del cliente actualizado a {value}"
            else:
                runtime.message = "No se pudo actualizar SERVER_HOST"
            continue
        if command == "c":
            device_id = prompt_line("Device ID: ")
            command_text = prompt_line("Comando a encolar: ")
            if device_id and command_text:
                runtime.message = queue_command(config_path, device_id, command_text)
            else:
                runtime.message = "Device ID y comando son obligatorios"
            continue

        runtime.message = f"Tecla sin accion: {command}"


if __name__ == "__main__":
    main()
