from __future__ import annotations

import calendar
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


def _add_months(value: datetime, months: int) -> datetime:
    if months < 0:
        raise ValueError("months must be >= 0")

    year_offset, month_index = divmod((value.month - 1) + months, 12)
    year = value.year + year_offset
    month = month_index + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def split_remaining_time(now: datetime, expires_at: datetime) -> dict[str, int]:
    if expires_at <= now:
        return {
            "years": 0,
            "months": 0,
            "days": 0,
            "hours": 0,
            "minutes": 0,
            "seconds": 0,
        }

    cursor = now
    years = 0
    while True:
        next_cursor = _add_months(cursor, 12)
        if next_cursor > expires_at:
            break
        years += 1
        cursor = next_cursor

    months = 0
    while True:
        next_cursor = _add_months(cursor, 1)
        if next_cursor > expires_at:
            break
        months += 1
        cursor = next_cursor

    remaining_seconds = max(0, int((expires_at - cursor).total_seconds()))
    days, remainder = divmod(remaining_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)

    return {
        "years": years,
        "months": months,
        "days": days,
        "hours": hours,
        "minutes": minutes,
        "seconds": seconds,
    }


def format_remaining_time(remaining_time: dict[str, int]) -> str:
    parts: list[str] = []
    units = (
        ("years", "y"),
        ("months", "mo"),
        ("days", "d"),
        ("hours", "h"),
        ("minutes", "m"),
        ("seconds", "s"),
    )

    for key, suffix in units:
        value = int(remaining_time.get(key, 0))
        if value > 0:
            parts.append(f"{value}{suffix}")

    return " ".join(parts) if parts else "0s"


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
    remaining_time = split_remaining_time(now, license_expires_dt)

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
            remaining_time=remaining_time,
        ),
        token_ttl_seconds=token_ttl_seconds,
        server_time=to_rfc3339(now),
    )
