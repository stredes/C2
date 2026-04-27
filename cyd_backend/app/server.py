from __future__ import annotations

import argparse
import json
import logging
import secrets
import socket
import subprocess
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


LOG = logging.getLogger("cyd_backend")

# Configuración de gategay
GATEGAY_BASE_IP = "192.168.1"
GATEGAY_START_IP = 33
GATEGAY_PORT = 8080


def check_internet_connection() -> bool:
    """Verifica si hay conexión a internet intentando conectar a 8.8.8.8"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        sock.connect(("8.8.8.8", 53))
        sock.close()
        return True
    except OSError:
        return False


def scan_local_network() -> list[int]:
    """Escanea la red local y retorna las IPs ocupadas en el segmento 192.168.1.x"""
    occupied = []
    try:
        # Obtener la IP local del servidor
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
        
        # Extraer el segmento de red
        parts = local_ip.split('.')
        if len(parts) >= 3:
            network_prefix = f"{parts[0]}.{parts[1]}.{parts[2]}"
        else:
            network_prefix = GATEGAY_BASE_IP
        
        # Escanear IPs del 1 al 254 usando ping
        for i in range(1, 255):
            ip = f"{network_prefix}.{i}"
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(0.3)
                result = sock.connect_ex((ip, 80))
                sock.close()
                if result == 0:
                    occupied.append(i)
            except OSError:
                pass
    except Exception as e:
        LOG.warning("Error escaneando red: %s", e)
    return occupied


def find_available_ip(start_from: int = GATEGAY_START_IP) -> int:
    """Encuentra la primera IP disponible a partir de start_from"""
    occupied = scan_local_network()
    for ip in range(start_from, 255):
        if ip not in occupied:
            return ip
    return start_from  # Retorna la IP por defecto si no encuentra


def start_gategay_service(ip: str) -> bool:
    """Inicia el servicio gategay en la IP especificada"""
    try:
        # Aquí puedes agregar la lógica específica para iniciar gategay
        # Por ejemplo, ejecutar un script o servicio
        LOG.info("Iniciando gategay en IP: %s", ip)
        # Simulación: aquí iría el comando para iniciar gategay
        # subprocess.Popen(["gategay", "-ip", ip, "-port", str(GATEGAY_PORT)])
        return True
    except Exception as e:
        LOG.error("Error iniciando gategay: %s", e)
        return False


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class BackendConfig:
    host: str
    port: int
    token_id: str
    secret_key: str
    data_dir: Path
    log_file: Path
    device_stale_seconds: int
    pc_cmd_enabled: bool
    pc_cmd_allowlist: list[str]
    pc_cmd_timeout_seconds: int


class BackendStore:
    def __init__(self, data_dir: Path, stale_after_seconds: int = 45) -> None:
        self.data_dir = data_dir
        self.devices_dir = data_dir / "devices"
        self.commands_dir = data_dir / "commands"
        self.results_dir = data_dir / "results"
        self.state_file = data_dir / "backend_state.json"
        self.stale_after_seconds = stale_after_seconds
        self._lock = threading.Lock()

        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.devices_dir.mkdir(parents=True, exist_ok=True)
        self.commands_dir.mkdir(parents=True, exist_ok=True)
        self.results_dir.mkdir(parents=True, exist_ok=True)

        if not self.state_file.exists():
            self._write_json(self.state_file, {"created_at": utc_now(), "devices": {}})

    def _read_json(self, path: Path, default: Any) -> Any:
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_json(self, path: Path, payload: Any) -> None:
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")

    def register_device(self, payload: dict[str, Any]) -> dict[str, Any]:
        device_id = payload["device_id"]
        now = utc_now()
        device_file = self.devices_dir / f"{device_id}.json"
        with self._lock:
            state = self._read_json(self.state_file, {"devices": {}})
            previous = state["devices"].get(device_id, {})
            device = {
                "device_id": device_id,
                "label": payload.get("label") or previous.get("label") or device_id,
                "platform": payload.get("platform", "esp32"),
                "ip": payload.get("ip"),
                "firmware": payload.get("firmware"),
                "registered_at": previous.get("registered_at", now),
                "last_seen": now,
                "status": "online",
            }
            state["devices"][device_id] = device
            self._write_json(self.state_file, state)
            self._write_json(device_file, device)
        
        # Verificar internet y configurar gategay si es necesario
        if payload.get("device_id") == "cyd-2432s028" or payload.get("platform") == "esp32":
            has_internet = check_internet_connection()
            if has_internet:
                # Verificar si 192.168.1.33 está disponible
                available_ip = find_available_ip(GATEGAY_START_IP)
                gategay_ip = f"{GATEGAY_BASE_IP}.{available_ip}"
                
                # Verificar si la IP preferida está ocupada
                preferred_occupied = GATEGAY_START_IP in scan_local_network()
                
                device["gategay"] = {
                    "enabled": True,
                    "ip": gategay_ip,
                    "port": GATEGAY_PORT,
                    "preferred_ip_used": preferred_occupied,
                    "internet_available": True
                }
                start_gategay_service(gategay_ip)
                LOG.info("Gategay iniciado en %s:%s (IP alternativa: %s)", gategay_ip, GATEGAY_PORT, "sí" if preferred_occupied else "no")
            else:
                device["gategay"] = {
                    "enabled": False,
                    "internet_available": False
                }
                LOG.info("Sin internet - gategay no iniciado")
            
            # Actualizar el archivo del dispositivo con info de gategay
            self._write_json(device_file, device)
        
        LOG.info("device registered device_id=%s ip=%s firmware=%s", device_id, device.get("ip"), device.get("firmware"))
        return device

    def heartbeat(self, payload: dict[str, Any]) -> dict[str, Any]:
        device_id = payload["device_id"]
        device_file = self.devices_dir / f"{device_id}.json"
        with self._lock:
            device = self._read_json(device_file, {"device_id": device_id})
            device.update(
                {
                    "label": payload.get("label", device.get("label", device_id)),
                    "platform": payload.get("platform", device.get("platform", "esp32")),
                    "ip": payload.get("ip", device.get("ip")),
                    "firmware": payload.get("firmware", device.get("firmware")),
                    "last_seen": utc_now(),
                    "status": payload.get("status", "online"),
                    "metrics": payload.get("metrics", {}),
                }
            )
            self._write_json(device_file, device)
            state = self._read_json(self.state_file, {"devices": {}})
            state.setdefault("devices", {})[device_id] = device
            self._write_json(self.state_file, state)
        LOG.info(
            "heartbeat device_id=%s status=%s ip=%s metrics=%s",
            device_id,
            device.get("status"),
            device.get("ip"),
            json.dumps(device.get("metrics", {}), ensure_ascii=True, sort_keys=True),
        )
        return device

    def queue_command(self, device_id: str, command: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        command_id = secrets.token_hex(8)
        payload = {
            "command_id": command_id,
            "device_id": device_id,
            "command": command,
            "args": args or {},
            "queued_at": utc_now(),
            "status": "queued",
        }
        command_file = self.commands_dir / f"{device_id}.json"
        with self._lock:
            queue = self._read_json(command_file, [])
            queue.append(payload)
            self._write_json(command_file, queue)
        LOG.info("command queued device_id=%s command_id=%s command=%s", device_id, command_id, command)
        return payload

    def pop_next_command(self, device_id: str) -> dict[str, Any] | None:
        command_file = self.commands_dir / f"{device_id}.json"
        with self._lock:
            queue = self._read_json(command_file, [])
            if not queue:
                return None
            command = queue.pop(0)
            command["status"] = "dispatched"
            command["dispatched_at"] = utc_now()
            self._write_json(command_file, queue)
        LOG.info(
            "command dispatched device_id=%s command_id=%s command=%s",
            device_id,
            command.get("command_id"),
            command.get("command"),
        )
        return command

    def save_result(self, payload: dict[str, Any]) -> dict[str, Any]:
        device_id = payload["device_id"]
        result_id = payload.get("result_id") or secrets.token_hex(8)
        result = {
            "result_id": result_id,
            "device_id": device_id,
            "command_id": payload.get("command_id"),
            "ok": bool(payload.get("ok", False)),
            "output": payload.get("output", ""),
            "received_at": utc_now(),
        }
        result_file = self.results_dir / f"{device_id}.json"
        with self._lock:
            entries = self._read_json(result_file, [])
            entries.append(result)
            self._write_json(result_file, entries)
        LOG.info(
            "result stored device_id=%s command_id=%s ok=%s output=%s",
            device_id,
            result.get("command_id"),
            result.get("ok"),
            str(result.get("output", ""))[:160],
        )
        return result

    def status(self) -> dict[str, Any]:
        with self._lock:
            state = self._read_json(self.state_file, {"devices": {}})

        devices = state.get("devices", {})
        summary = {
            "device_count": len(devices),
            "online_count": 0,
            "stale_count": 0,
            "offline_count": 0,
        }
        now = datetime.now(timezone.utc)
        for device in devices.values():
            last_seen_raw = device.get("last_seen")
            derived_status = device.get("status", "unknown")
            age_seconds = None
            if isinstance(last_seen_raw, str):
                try:
                    age_seconds = int((now - datetime.fromisoformat(last_seen_raw)).total_seconds())
                except ValueError:
                    age_seconds = None
            if age_seconds is not None:
                device["age_seconds"] = age_seconds
                if age_seconds > 0 and age_seconds > self.stale_after_seconds and derived_status == "online":
                    derived_status = "stale"
            device["derived_status"] = derived_status
            if derived_status == "online":
                summary["online_count"] += 1
            elif derived_status == "stale":
                summary["stale_count"] += 1
            else:
                summary["offline_count"] += 1

        state["summary"] = summary
        return state


def load_config(config_path: Path) -> BackendConfig:
    raw = json.loads(config_path.read_text(encoding="utf-8-sig"))
    root_dir = config_path.parent.parent.resolve()
    data_dir = (root_dir / raw.get("data_dir", "data")).resolve()
    log_file = (root_dir / raw.get("log_file", "data/backend.log")).resolve()
    return BackendConfig(
        host=raw.get("host", "0.0.0.0"),
        port=int(raw.get("port", 8080)),
        token_id=raw["token_id"],
        secret_key=raw["secret_key"],
        data_dir=data_dir,
        log_file=log_file,
        device_stale_seconds=int(raw.get("device_stale_seconds", 45)),
        pc_cmd_enabled=bool(raw.get("pc_cmd_enabled", False)),
        pc_cmd_allowlist=[str(item).lower() for item in raw.get("pc_cmd_allowlist", [])],
        pc_cmd_timeout_seconds=int(raw.get("pc_cmd_timeout_seconds", 8)),
    )


def validate_pc_command(command: str, allowlist: list[str]) -> tuple[bool, str]:
    command = command.strip()
    if not command:
        return False, "command required"
    if any(char in command for char in ["&", "|", "<", ">", "^", "\n", "\r"]):
        return False, "shell metacharacters are blocked"
    first_token = command.split(None, 1)[0].lower()
    if first_token not in allowlist:
        return False, f"command not allowed: {first_token}"
    return True, ""


def run_pc_command(command: str, timeout_seconds: int) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            ["cmd.exe", "/d", "/s", "/c", command],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "exit_code": None, "output": f"timeout after {timeout_seconds}s"}
    except OSError as exc:
        return {"ok": False, "exit_code": None, "output": str(exc)}

    output = "\n".join(part for part in [completed.stdout.rstrip(), completed.stderr.rstrip()] if part)
    if len(output) > 4096:
        output = output[:4096] + "\n[truncated]"
    return {"ok": completed.returncode == 0, "exit_code": completed.returncode, "output": output}


class BackendHandler(BaseHTTPRequestHandler):
    server_version = "CYDBackend/0.1"

    @property
    def backend(self) -> "BackendHTTPServer":
        return self.server  # type: ignore[return-value]

    def log_message(self, format: str, *args: Any) -> None:
        LOG.info("%s - %s", self.address_string(), format % args)

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def _authorized(self) -> bool:
        token_id = self.headers.get("X-Token-Id", "")
        secret_key = self.headers.get("X-Secret-Key", "")
        return token_id == self.backend.config.token_id and secrets.compare_digest(
            secret_key, self.backend.config.secret_key
        )

    def _require_auth(self) -> bool:
        if self._authorized():
            return True
        self._send_json(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": "unauthorized"})
        return False

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)

        if parsed.path == "/health":
            self._send_json(
                HTTPStatus.OK,
                {"ok": True, "status": "ok", "service": "cyd-backend", "time": utc_now()},
            )
            return

        if parsed.path == "/api/v1/status":
            if not self._require_auth():
                return
            state = self.backend.store.status()
            # Agregar información de gategay al estado
            state["gategay"] = {
                "internet_available": check_internet_connection(),
                "base_ip": GATEGAY_BASE_IP,
                "port": GATEGAY_PORT,
                "preferred_ip": f"{GATEGAY_BASE_IP}.{GATEGAY_START_IP}",
                "current_available_ip": f"{GATEGAY_BASE_IP}.{find_available_ip(GATEGAY_START_IP)}"
            }
            self._send_json(HTTPStatus.OK, {"ok": True, "state": state})
            return

        if parsed.path == "/api/v1/commands":
            if not self._require_auth():
                return
            query = parse_qs(parsed.query)
            device_id = query.get("device_id", [""])[0]
            if not device_id:
                self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "device_id required"})
                return
            command = self.backend.store.pop_next_command(device_id)
            self._send_json(HTTPStatus.OK, {"ok": True, "command": command})
            return

        self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if not self._require_auth():
            return

        payload = self._read_json_body()

        if self.path == "/api/v1/register":
            if "device_id" not in payload:
                self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "device_id required"})
                return
            device = self.backend.store.register_device(payload)
            self._send_json(HTTPStatus.OK, {"ok": True, "device": device})
            return

        if self.path == "/api/v1/heartbeat":
            if "device_id" not in payload:
                self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "device_id required"})
                return
            device = self.backend.store.heartbeat(payload)
            self._send_json(HTTPStatus.OK, {"ok": True, "device": device})
            return

        if self.path == "/api/v1/results":
            if "device_id" not in payload:
                self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "device_id required"})
                return
            result = self.backend.store.save_result(payload)
            self._send_json(HTTPStatus.OK, {"ok": True, "result": result})
            return

        if self.path == "/api/v1/pc/cmd":
            if not self.backend.config.pc_cmd_enabled:
                self._send_json(HTTPStatus.FORBIDDEN, {"ok": False, "error": "pc_cmd disabled"})
                return
            command = str(payload.get("command", "")).strip()
            valid, error = validate_pc_command(command, self.backend.config.pc_cmd_allowlist)
            if not valid:
                self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": error})
                return
            result = run_pc_command(command, self.backend.config.pc_cmd_timeout_seconds)
            LOG.info(
                "pc cmd device_id=%s ok=%s exit_code=%s command=%s",
                payload.get("device_id", "-"),
                result.get("ok"),
                result.get("exit_code"),
                command,
            )
            self._send_json(HTTPStatus.OK, result)
            return

        self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not found"})


class BackendHTTPServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], handler_class: type[BackendHandler], config: BackendConfig):
        super().__init__(server_address, handler_class)
        self.config = config
        self.store = BackendStore(config.data_dir, stale_after_seconds=config.device_stale_seconds)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local backend for CYD/Bruce HTTP connections")
    parser.add_argument("--config", default="config/backend.json", help="Path to backend config JSON")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    config_path = Path(args.config).resolve()
    config = load_config(config_path)
    config.log_file.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(config.log_file, encoding="utf-8"),
        ],
    )
    server = BackendHTTPServer((config.host, config.port), BackendHandler, config)
    LOG.info("CYD backend listening on %s:%s", config.host, config.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        LOG.info("Stopping CYD backend")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
