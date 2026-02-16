from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.db import get_license
from app.models import DeniedReason, LeaseInfo, LicenseInfo, TokenAllowedResponse, TokenDeniedResponse


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def to_rfc3339(value: datetime) -> str:
    utc_value = value.astimezone(timezone.utc).replace(microsecond=0)
    return utc_value.isoformat().replace("+00:00", "Z")


def parse_rfc3339(value: str) -> datetime:
    candidate = value.strip()
    if candidate.endswith("Z"):
        candidate = f"{candidate[:-1]}+00:00"

    parsed = datetime.fromisoformat(candidate)
    if parsed.tzinfo is None:
        raise ValueError("Timestamp must include timezone information")

    return parsed.astimezone(timezone.utc)


def _denied(reason: DeniedReason, now: datetime) -> TokenDeniedResponse:
    return TokenDeniedResponse(
        allowed=False,
        reason=reason,
        server_time=to_rfc3339(now),
    )


def issue_token(
    db_path: str,
    token_ttl_seconds: int,
    license_key: str,
    app_id: str | None = None,
    app_version: str | None = None,
) -> TokenAllowedResponse | TokenDeniedResponse:
    del app_id, app_version

    now = utc_now()
    record = get_license(db_path, license_key)
    if record is None:
        return _denied("not_found", now)

    if record.status == "disabled":
        return _denied("disabled", now)

    issued_at = parse_rfc3339(record.issued_at)
    license_expires_dt = issued_at + timedelta(days=record.duration_days)
    if now >= license_expires_dt:
        return _denied("expired", now)

    lease_issued_at = now
    lease_expires_at = lease_issued_at + timedelta(seconds=token_ttl_seconds)
    days_remaining_seconds = (license_expires_dt - now).total_seconds()
    days_left = max(0, math.floor(days_remaining_seconds / 86400))

    return TokenAllowedResponse(
        allowed=True,
        lease=LeaseInfo(
            lease_id=str(uuid4()),
            issued_at=to_rfc3339(lease_issued_at),
            expires_at=to_rfc3339(lease_expires_at),
        ),
        license=LicenseInfo(
            license_key=record.license_key,
            issued_at=to_rfc3339(issued_at),
            duration_days=record.duration_days,
            license_expires_at=to_rfc3339(license_expires_dt),
            days_left=days_left,
        ),
        token_ttl_seconds=token_ttl_seconds,
        server_time=to_rfc3339(now),
    )
