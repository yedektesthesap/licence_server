from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    db_path: str
    token_ttl_seconds: int
    host: str
    port: int
    admin_username: str | None
    admin_password: str | None

    @property
    def admin_enabled(self) -> bool:
        return bool(self.admin_username and self.admin_password)


def _parse_int(value: str, name: str) -> int:
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _parse_optional_str(value: str | None) -> str | None:
    if value is None:
        return None
    candidate = value.strip()
    return candidate or None


def get_settings() -> Settings:
    db_path = os.getenv("DB_PATH", "./data/licenses.db")
    token_ttl_seconds = _parse_int(os.getenv("TOKEN_TTL_SECONDS", "86400"), "TOKEN_TTL_SECONDS")
    host = os.getenv("HOST", "0.0.0.0")
    port = _parse_int(os.getenv("PORT", "8000"), "PORT")
    admin_username = _parse_optional_str(os.getenv("ADMIN_USERNAME"))
    admin_password = _parse_optional_str(os.getenv("ADMIN_PASSWORD"))

    if token_ttl_seconds < 1:
        raise ValueError("TOKEN_TTL_SECONDS must be >= 1")

    if port < 1 or port > 65535:
        raise ValueError("PORT must be between 1 and 65535")

    if (admin_username is None) != (admin_password is None):
        raise ValueError("ADMIN_USERNAME and ADMIN_PASSWORD must be set together")

    return Settings(
        db_path=db_path,
        token_ttl_seconds=token_ttl_seconds,
        host=host,
        port=port,
        admin_username=admin_username,
        admin_password=admin_password,
    )
