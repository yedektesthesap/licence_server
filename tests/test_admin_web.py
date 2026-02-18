from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.db import get_license, init_db, insert_license, list_licenses
from app.models import LicenseRecord
from app.service import parse_rfc3339, to_rfc3339, utc_now


@pytest.fixture()
def db_path(tmp_path, monkeypatch) -> str:
    path = tmp_path / "licenses.db"
    monkeypatch.setenv("DB_PATH", str(path))
    monkeypatch.setenv("TOKEN_TTL_SECONDS", "86400")
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "secret-pass")
    init_db(str(path))
    return str(path)


@pytest.fixture()
def client(db_path: str) -> TestClient:
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


def test_admin_dashboard_requires_auth(client: TestClient) -> None:
    response = client.get("/admin", follow_redirects=False)
    assert response.status_code == 401


def test_admin_dashboard_lists_licenses(client: TestClient, db_path: str) -> None:
    record = LicenseRecord(
        license_key="ABCD-EFGH-JKLM",
        issued_at=to_rfc3339(utc_now() - timedelta(days=2)),
        duration_days=30,
        status="active",
        note="demo",
    )
    insert_license(db_path, record)

    response = client.get("/admin", auth=("admin", "secret-pass"))
    assert response.status_code == 200
    assert "CCM License Admin" in response.text
    assert "ABCD-EFGH-JKLM" in response.text
    assert "demo" in response.text


def test_admin_create_disable_and_enable_license(client: TestClient, db_path: str) -> None:
    create_response = client.post(
        "/admin/licenses",
        auth=("admin", "secret-pass"),
        data={"days": "7", "note": "trial"},
        follow_redirects=False,
    )
    assert create_response.status_code == 303

    records = list_licenses(db_path)
    assert len(records) == 1
    created_key = records[0].license_key
    assert records[0].status == "active"
    assert records[0].note == "trial"

    disable_response = client.post(
        f"/admin/licenses/{created_key}/disable",
        auth=("admin", "secret-pass"),
        follow_redirects=False,
    )
    assert disable_response.status_code == 303

    updated = get_license(db_path, created_key)
    assert updated is not None
    assert updated.status == "disabled"

    enable_response = client.post(
        f"/admin/licenses/{created_key}/enable",
        auth=("admin", "secret-pass"),
        follow_redirects=False,
    )
    assert enable_response.status_code == 303

    reenabled = get_license(db_path, created_key)
    assert reenabled is not None
    assert reenabled.status == "active"


def test_admin_generate_key_prefills_form(client: TestClient) -> None:
    response = client.post(
        "/admin/licenses/generate-key",
        auth=("admin", "secret-pass"),
        follow_redirects=False,
    )
    assert response.status_code == 303
    location = response.headers["location"]
    assert "key=" in location

    dashboard = client.get(location, auth=("admin", "secret-pass"))
    assert dashboard.status_code == 200
    assert 'name="key"' in dashboard.text


def test_admin_licenses_endpoint_marks_expired_as_enable_action(
    client: TestClient, db_path: str
) -> None:
    expired_key = "EXPD-TEST-0001"
    insert_license(
        db_path,
        LicenseRecord(
            license_key=expired_key,
            issued_at=to_rfc3339(utc_now() - timedelta(days=4)),
            duration_days=1,
            status="active",
            note="old trial",
        ),
    )

    response = client.get("/admin/licenses", auth=("admin", "secret-pass"))
    assert response.status_code == 200

    payload = response.json()
    item = next(row for row in payload["licenses"] if row["license_key"] == expired_key)
    assert item["is_expired"] is True
    assert item["display_status"] == "disabled"
    assert item["action_mode"] == "enable"
    assert item["requires_duration"] is True
    assert item["update_remaining_action"].endswith(f"/admin/licenses/{expired_key}/remaining-time")


def test_admin_dashboard_renders_remaining_time_editor_trigger(
    client: TestClient, db_path: str
) -> None:
    insert_license(
        db_path,
        LicenseRecord(
            license_key="EXPD-TEST-0003",
            issued_at=to_rfc3339(utc_now() - timedelta(days=10)),
            duration_days=1,
            status="active",
            note="expired-ui",
        ),
    )

    response = client.get("/admin", auth=("admin", "secret-pass"))
    assert response.status_code == 200
    assert "remaining-time-trigger is-expired" in response.text
    assert f'data-update-action="http://testserver/admin/licenses/EXPD-TEST-0003/remaining-time"' in response.text
    assert 'data-requires-duration="1"' in response.text
    assert "duration-picker" not in response.text


def test_admin_update_remaining_time_then_enable_expired_license(
    client: TestClient, db_path: str
) -> None:
    expired_key = "EXPD-TEST-0002"
    original_issued_at = to_rfc3339(utc_now() - timedelta(days=3))
    insert_license(
        db_path,
        LicenseRecord(
            license_key=expired_key,
            issued_at=original_issued_at,
            duration_days=1,
            status="disabled",
            note="expired",
        ),
    )

    blocked_enable = client.post(
        f"/admin/licenses/{expired_key}/enable",
        auth=("admin", "secret-pass"),
        follow_redirects=False,
    )
    assert blocked_enable.status_code == 303

    unchanged = get_license(db_path, expired_key)
    assert unchanged is not None
    assert unchanged.status == "disabled"
    assert unchanged.duration_days == 1
    assert unchanged.issued_at == original_issued_at

    update_remaining = client.post(
        f"/admin/licenses/{expired_key}/remaining-time",
        auth=("admin", "secret-pass"),
        data={"days": "30"},
    )
    assert update_remaining.status_code == 200
    assert update_remaining.json()["ok"] is True

    updated = get_license(db_path, expired_key)
    assert updated is not None
    assert updated.status == "disabled"
    assert updated.duration_days == 30
    assert parse_rfc3339(updated.issued_at) > parse_rfc3339(original_issued_at)

    enable_response = client.post(
        f"/admin/licenses/{expired_key}/enable",
        auth=("admin", "secret-pass"),
        follow_redirects=False,
    )
    assert enable_response.status_code == 303

    enabled = get_license(db_path, expired_key)
    assert enabled is not None
    assert enabled.status == "active"
