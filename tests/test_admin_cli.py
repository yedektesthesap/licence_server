from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from app.db import get_license, init_db
from app.service import parse_rfc3339

ROOT = Path(__file__).resolve().parents[1]


def run_cli(args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "app.admin", *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_create_license_disable_and_enable(tmp_path) -> None:
    db_path = tmp_path / "licenses.db"
    env = os.environ.copy()
    env["DB_PATH"] = str(db_path)

    create_result = run_cli(["create-license", "--days", "7", "--note", "first"], env)
    assert create_result.returncode == 0, create_result.stderr

    payload = json.loads(create_result.stdout)
    assert re.fullmatch(r"[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}", payload["license_key"])
    assert payload["status"] == "active"
    assert payload["duration_days"] == 7
    assert payload["license_expires_at"].endswith("Z")

    record = get_license(str(db_path), payload["license_key"])
    assert record is not None
    assert record.status == "active"

    issued_at = parse_rfc3339(payload["issued_at"])
    expires_at = parse_rfc3339(payload["license_expires_at"])
    assert int((expires_at - issued_at).total_seconds()) == 7 * 86400

    disable_result = run_cli(["disable-license", "--key", payload["license_key"]], env)
    assert disable_result.returncode == 0, disable_result.stderr

    disabled_record = get_license(str(db_path), payload["license_key"])
    assert disabled_record is not None
    assert disabled_record.status == "disabled"

    enable_result = run_cli(["enable-license", "--key", payload["license_key"]], env)
    assert enable_result.returncode == 0, enable_result.stderr

    reenabled_record = get_license(str(db_path), payload["license_key"])
    assert reenabled_record is not None
    assert reenabled_record.status == "active"


def test_list_and_show_license(tmp_path) -> None:
    db_path = tmp_path / "licenses.db"
    env = os.environ.copy()
    env["DB_PATH"] = str(db_path)

    init_db(str(db_path))
    create_result = run_cli(
        ["create-license", "--days", "3", "--key", "ABCD-EFGH-JKLM", "--note", "demo"],
        env,
    )
    assert create_result.returncode == 0, create_result.stderr

    list_result = run_cli(["list-licenses"], env)
    assert list_result.returncode == 0, list_result.stderr
    list_payload = json.loads(list_result.stdout)
    assert isinstance(list_payload, list)
    assert len(list_payload) == 1
    assert list_payload[0]["license_key"] == "ABCD-EFGH-JKLM"

    show_result = run_cli(["show-license", "--key", "ABCD-EFGH-JKLM"], env)
    assert show_result.returncode == 0, show_result.stderr
    show_payload = json.loads(show_result.stdout)
    assert show_payload["license_key"] == "ABCD-EFGH-JKLM"
    assert show_payload["status"] == "active"


def test_disable_missing_license_returns_non_zero(tmp_path) -> None:
    db_path = tmp_path / "licenses.db"
    env = os.environ.copy()
    env["DB_PATH"] = str(db_path)

    result = run_cli(["disable-license", "--key", "MISS-ING1-KEY2"], env)
    assert result.returncode != 0
    assert "not found" in result.stderr.lower()


def test_generate_key_returns_valid_format(tmp_path) -> None:
    db_path = tmp_path / "licenses.db"
    env = os.environ.copy()
    env["DB_PATH"] = str(db_path)

    result = run_cli(["generate-key"], env)
    assert result.returncode == 0, result.stderr

    payload = json.loads(result.stdout)
    assert re.fullmatch(r"[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}", payload["license_key"])
