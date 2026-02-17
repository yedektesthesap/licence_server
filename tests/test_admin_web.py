from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.db import get_license, init_db, insert_license, list_licenses
from app.models import LicenseRecord
from app.service import to_rfc3339, utc_now


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
