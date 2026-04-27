#!/data/data/com.termux/files/usr/bin/bash
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
CONFIG_PATH="${1:-"$ROOT_DIR/config/backend.termux.json"}"

printf 'DEBUG: Buscando config en: %s\n' "$CONFIG_PATH" >&2
if [ ! -f "$CONFIG_PATH" ]; then
  printf 'No existe el archivo de config: %s\n' "$CONFIG_PATH" >&2
  printf 'Copia primero config/backend.termux.json.example a config/backend.termux.json\n' >&2
  exit 1
fi

mkdir -p "$ROOT_DIR/data/devices" "$ROOT_DIR/data/commands" "$ROOT_DIR/data/results"

printf 'CYD backend root : %s\n' "$ROOT_DIR"
printf 'Config activa    : %s\n' "$CONFIG_PATH"

if command -v ip >/dev/null 2>&1; then
  WLAN_IP="$(ip -4 addr show wlan0 2>/dev/null | awk '/inet / {print $2}' | cut -d/ -f1 | head -n1)"
  if [ -n "${WLAN_IP:-}" ]; then
    printf 'URL sugerida     : http://%s:%s/health\n' "$WLAN_IP" "$(python - <<'PY' "$CONFIG_PATH"
import json
import sys
from pathlib import Path

config = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(config.get("port", 8000))
PY
)"
  fi
fi

cd "$ROOT_DIR"
exec python "$ROOT_DIR/scripts/run_backend.py" --config "$CONFIG_PATH"
