from __future__ import annotations

import random
import sqlite3
from datetime import timedelta
from typing import Any

from app.db import insert_license
from app.models import LicenseRecord
from app.service import parse_rfc3339, to_rfc3339, utc_now

KEY_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
KEY_SEGMENT_LENGTH = 4
KEY_SEGMENTS = 3
KEY_GENERATION_ATTEMPTS = 100


def format_license(record: LicenseRecord) -> dict[str, Any]:
    issued_at = parse_rfc3339(record.issued_at)
    license_expires_at = issued_at + timedelta(days=record.duration_days)
    return {
        "license_key": record.license_key,
        "issued_at": to_rfc3339(issued_at),
        "duration_days": record.duration_days,
        "license_expires_at": to_rfc3339(license_expires_at),
        "status": record.status,
        "note": record.note,
    }


def generate_key() -> str:
    segments: list[str] = []
    for _ in range(KEY_SEGMENTS):
        segment = "".join(random.choice(KEY_ALPHABET) for _ in range(KEY_SEGMENT_LENGTH))
        segments.append(segment)
    return "-".join(segments)


def create_license(
    db_path: str,
    *,
    days: int,
    key: str | None = None,
    note: str | None = None,
) -> LicenseRecord:
    if days < 1:
        raise ValueError("--days must be >= 1")

    issued_at_rfc3339 = to_rfc3339(utc_now())
    normalized_note = note if note else None

    if key is not None:
        candidate_key = key.strip()
        if not candidate_key:
            raise ValueError("--key must be non-empty")
        record = LicenseRecord(
            license_key=candidate_key,
            issued_at=issued_at_rfc3339,
            duration_days=days,
            status="active",
            note=normalized_note,
        )
        insert_license(db_path, record)
        return record

    for _ in range(KEY_GENERATION_ATTEMPTS):
        generated_key = generate_key()
        candidate = LicenseRecord(
            license_key=generated_key,
            issued_at=issued_at_rfc3339,
            duration_days=days,
            status="active",
            note=normalized_note,
        )
        try:
            insert_license(db_path, candidate)
            return candidate
        except sqlite3.IntegrityError:
            continue

    raise RuntimeError("Failed to generate a unique license key")
