from __future__ import annotations

import sqlite3
from pathlib import Path

from app.models import LicenseRecord


def connect(db_path: str) -> sqlite3.Connection:
    path = Path(db_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str) -> None:
    with connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS licenses (
                license_key TEXT PRIMARY KEY,
                issued_at TEXT NOT NULL,
                duration_days INTEGER NOT NULL CHECK(duration_days >= 1),
                status TEXT NOT NULL CHECK(status IN ('active', 'disabled')),
                note TEXT NULL
            )
            """
        )
        conn.commit()


def _row_to_license(row: sqlite3.Row) -> LicenseRecord:
    return LicenseRecord(
        license_key=row["license_key"],
        issued_at=row["issued_at"],
        duration_days=int(row["duration_days"]),
        status=row["status"],
        note=row["note"],
    )


def get_license(db_path: str, key: str) -> LicenseRecord | None:
    with connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT license_key, issued_at, duration_days, status, note
            FROM licenses
            WHERE license_key = ?
            """,
            (key,),
        ).fetchone()

    if row is None:
        return None

    return _row_to_license(row)


def insert_license(db_path: str, record: LicenseRecord) -> None:
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO licenses (license_key, issued_at, duration_days, status, note)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                record.license_key,
                record.issued_at,
                record.duration_days,
                record.status,
                record.note,
            ),
        )
        conn.commit()


def disable_license(db_path: str, key: str) -> bool:
    return _set_license_status(db_path, key, "disabled")


def enable_license(db_path: str, key: str) -> bool:
    return _set_license_status(db_path, key, "active")


def reactivate_license(db_path: str, key: str, *, issued_at: str, duration_days: int) -> bool:
    with connect(db_path) as conn:
        cursor = conn.execute(
            """
            UPDATE licenses
            SET issued_at = ?, duration_days = ?, status = 'active'
            WHERE license_key = ?
            """,
            (issued_at, duration_days, key),
        )
        conn.commit()

    return cursor.rowcount > 0


def update_license_duration(
    db_path: str,
    key: str,
    *,
    issued_at: str,
    duration_days: int,
) -> bool:
    with connect(db_path) as conn:
        cursor = conn.execute(
            """
            UPDATE licenses
            SET issued_at = ?, duration_days = ?
            WHERE license_key = ?
            """,
            (issued_at, duration_days, key),
        )
        conn.commit()

    return cursor.rowcount > 0


def _set_license_status(db_path: str, key: str, status: str) -> bool:
    with connect(db_path) as conn:
        cursor = conn.execute(
            """
            UPDATE licenses
            SET status = ?
            WHERE license_key = ?
            """,
            (status, key),
        )
        conn.commit()

    return cursor.rowcount > 0


def list_licenses(db_path: str) -> list[LicenseRecord]:
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT license_key, issued_at, duration_days, status, note
            FROM licenses
            ORDER BY issued_at DESC, license_key ASC
            """
        ).fetchall()

    return [_row_to_license(row) for row in rows]
