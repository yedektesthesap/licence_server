from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from typing import Any

from app.db import disable_license, enable_license, get_license, init_db, list_licenses
from app.license_admin import create_license, format_license, generate_unique_key
from app.settings import get_settings

def _print_json(data: Any) -> None:
    print(json.dumps(data, separators=(",", ":"), sort_keys=False))


def _handle_create_license(args: argparse.Namespace) -> int:
    settings = get_settings()
    init_db(settings.db_path)

    try:
        record = create_license(
            settings.db_path,
            days=args.days,
            key=args.key,
            note=args.note,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except sqlite3.IntegrityError:
        duplicate_key = args.key.strip() if args.key else args.key
        print(f"License key already exists: {duplicate_key}", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    _print_json(format_license(record))
    return 0


def _handle_disable_license(args: argparse.Namespace) -> int:
    settings = get_settings()
    init_db(settings.db_path)

    updated = disable_license(settings.db_path, args.key)
    if not updated:
        print(f"License key not found: {args.key}", file=sys.stderr)
        return 1

    _print_json({"license_key": args.key, "status": "disabled"})
    return 0


def _handle_enable_license(args: argparse.Namespace) -> int:
    settings = get_settings()
    init_db(settings.db_path)

    updated = enable_license(settings.db_path, args.key)
    if not updated:
        print(f"License key not found: {args.key}", file=sys.stderr)
        return 1

    _print_json({"license_key": args.key, "status": "active"})
    return 0


def _handle_generate_key(_: argparse.Namespace) -> int:
    settings = get_settings()
    init_db(settings.db_path)
    _print_json({"license_key": generate_unique_key(settings.db_path)})
    return 0


def _handle_list_licenses(_: argparse.Namespace) -> int:
    settings = get_settings()
    init_db(settings.db_path)

    records = list_licenses(settings.db_path)
    payload = [format_license(record) for record in records]
    _print_json(payload)
    return 0


def _handle_show_license(args: argparse.Namespace) -> int:
    settings = get_settings()
    init_db(settings.db_path)

    record = get_license(settings.db_path, args.key)
    if record is None:
        print(f"License key not found: {args.key}", file=sys.stderr)
        return 1

    _print_json(format_license(record))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.admin")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create-license")
    create_parser.add_argument("--days", type=int, required=True)
    create_parser.add_argument("--key", type=str)
    create_parser.add_argument("--note", type=str)
    create_parser.set_defaults(handler=_handle_create_license)

    disable_parser = subparsers.add_parser("disable-license")
    disable_parser.add_argument("--key", type=str, required=True)
    disable_parser.set_defaults(handler=_handle_disable_license)

    enable_parser = subparsers.add_parser("enable-license")
    enable_parser.add_argument("--key", type=str, required=True)
    enable_parser.set_defaults(handler=_handle_enable_license)

    generate_parser = subparsers.add_parser("generate-key")
    generate_parser.set_defaults(handler=_handle_generate_key)

    list_parser = subparsers.add_parser("list-licenses")
    list_parser.set_defaults(handler=_handle_list_licenses)

    show_parser = subparsers.add_parser("show-license")
    show_parser.add_argument("--key", type=str, required=True)
    show_parser.set_defaults(handler=_handle_show_license)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
