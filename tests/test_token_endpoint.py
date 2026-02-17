from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.db import init_db, insert_license
from app.models import LicenseRecord
from app.service import format_remaining_time, parse_rfc3339, split_remaining_time, to_rfc3339, utc_now


@pytest.fixture()
def db_path(tmp_path, monkeypatch) -> str:
    path = tmp_path / "licenses.db"
    monkeypatch.setenv("DB_PATH", str(path))
    monkeypatch.setenv("TOKEN_TTL_SECONDS", "86400")
    init_db(str(path))
    return str(path)


@pytest.fixture()
def client(db_path: str) -> TestClient:
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


def seed_license(
    db_path: str,
    *,
    license_key: str,
    issued_at_offset: timedelta,
    duration_days: int,
    status: str,
) -> None:
    issued_at = utc_now() - issued_at_offset
    record = LicenseRecord(
        license_key=license_key,
        issued_at=to_rfc3339(issued_at),
        duration_days=duration_days,
        status=status,
        note=None,
    )
    insert_license(db_path, record)


def test_token_allows_active_license(client: TestClient, db_path: str) -> None:
    seed_license(
        db_path,
        license_key="ABCD-EFGH-JKLM",
        issued_at_offset=timedelta(days=1),
        duration_days=30,
        status="active",
    )

    response = client.post(
        "/v1/token",
        json={
            "license_key": "ABCD-EFGH-JKLM",
            "app_id": "ccm",
            "app_version": "1.0.0",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["allowed"] is True
    assert payload["token_ttl_seconds"] == 86400
    assert payload["license"]["license_key"] == "ABCD-EFGH-JKLM"
    assert payload["license"]["duration_days"] == 30
    assert set(payload["license"]["remaining_time"]) == {
        "years",
        "months",
        "days",
        "hours",
        "minutes",
        "seconds",
    }
    assert any(value > 0 for value in payload["license"]["remaining_time"].values())
    assert payload["license"]["remaining_time"] == split_remaining_time(
        parse_rfc3339(payload["server_time"]),
        parse_rfc3339(payload["license"]["license_expires_at"]),
    )
    assert payload["server_time"].endswith("Z")

    lease_issued_at = parse_rfc3339(payload["lease"]["issued_at"])
    lease_expires_at = parse_rfc3339(payload["lease"]["expires_at"])
    assert int((lease_expires_at - lease_issued_at).total_seconds()) == 86400


def test_token_denies_disabled_license(client: TestClient, db_path: str) -> None:
    seed_license(
        db_path,
        license_key="DISA-BLED-KEY1",
        issued_at_offset=timedelta(days=1),
        duration_days=30,
        status="disabled",
    )

    response = client.post("/v1/token", json={"license_key": "DISA-BLED-KEY1"})

    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "allowed": False,
        "reason": "disabled",
        "server_time": payload["server_time"],
    }
    assert payload["server_time"].endswith("Z")


def test_token_denies_expired_license(client: TestClient, db_path: str) -> None:
    seed_license(
        db_path,
        license_key="EXPI-REDK-EY12",
        issued_at_offset=timedelta(days=10),
        duration_days=1,
        status="active",
    )

    response = client.post("/v1/token", json={"license_key": "EXPI-REDK-EY12"})

    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "allowed": False,
        "reason": "expired",
        "server_time": payload["server_time"],
    }
    assert payload["server_time"].endswith("Z")


def test_token_denies_unknown_license(client: TestClient) -> None:
    response = client.post("/v1/token", json={"license_key": "NOPE-NOPE-NOPE"})

    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "allowed": False,
        "reason": "not_found",
        "server_time": payload["server_time"],
    }
    assert payload["server_time"].endswith("Z")


def test_remaining_time_components_and_min_zero(client: TestClient, db_path: str) -> None:
    seed_license(
        db_path,
        license_key="FLOO-RDAY-SLFT",
        issued_at_offset=timedelta(days=9, hours=23),
        duration_days=10,
        status="active",
    )

    response = client.post("/v1/token", json={"license_key": "FLOO-RDAY-SLFT"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["allowed"] is True
    remaining_time = payload["license"]["remaining_time"]
    assert remaining_time["years"] == 0
    assert remaining_time["months"] == 0
    assert remaining_time["days"] == 0
    assert all(value >= 0 for value in remaining_time.values())
    assert (
        remaining_time["hours"] > 0
        or remaining_time["minutes"] > 0
        or remaining_time["seconds"] > 0
    )


def test_format_remaining_time_omits_zero_components() -> None:
    assert (
        format_remaining_time(
            {
                "years": 0,
                "months": 0,
                "days": 17,
                "hours": 4,
                "minutes": 0,
                "seconds": 9,
            }
        )
        == "17d 4h 9s"
    )
    assert (
        format_remaining_time(
            {
                "years": 0,
                "months": 0,
                "days": 0,
                "hours": 0,
                "minutes": 0,
                "seconds": 0,
            }
        )
        == "0s"
    )
