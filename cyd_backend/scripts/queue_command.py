from __future__ import annotations

import argparse
import json
import pathlib
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
APP = ROOT / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from server import BackendStore, load_config


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Queue a command for a CYD device")
    parser.add_argument("--config", default="config/backend.json", help="Path to backend config JSON")
    parser.add_argument("--device", required=True, help="Device ID")
    parser.add_argument("--command", required=True, help="Command string")
    parser.add_argument("--args-json", default="{}", help="Command args JSON")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    config = load_config((ROOT / args.config).resolve())
    store = BackendStore(config.data_dir)
    payload = store.queue_command(args.device, args.command, json.loads(args.args_json))
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
