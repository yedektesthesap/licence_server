from __future__ import annotations

import secrets
import sqlite3
from datetime import timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates

from app.db import disable_license, enable_license, get_license, init_db, list_licenses, reactivate_license
from app.license_admin import create_license, format_license, generate_unique_key
from app.service import format_remaining_time, parse_rfc3339, split_remaining_time, to_rfc3339, utc_now
from app.settings import get_settings

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
router = APIRouter(prefix="/admin", tags=["admin"])
basic_auth = HTTPBasic()


def _require_admin(credentials: HTTPBasicCredentials = Depends(basic_auth)) -> str:
    settings = get_settings()
    if not settings.admin_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin panel is disabled. Set ADMIN_USERNAME and ADMIN_PASSWORD.",
        )

    expected_username = settings.admin_username or ""
    expected_password = settings.admin_password or ""
    username_valid = secrets.compare_digest(credentials.username, expected_username)
    password_valid = secrets.compare_digest(credentials.password, expected_password)

    if not (username_valid and password_valid):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials",
            headers={"WWW-Authenticate": "Basic"},
        )

    return credentials.username


def _redirect_to_dashboard(
    request: Request,
    *,
    message: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    query = {}
    if message:
        query["message"] = message
    if error:
        query["error"] = error

    base_url = str(request.url_for("admin_dashboard"))
    redirect_url = f"{base_url}?{urlencode(query)}" if query else base_url
    return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)


def _build_license_rows(request: Request, db_path: str) -> list[dict[str, Any]]:
    now = utc_now()
    rows = []

    for record in list_licenses(db_path):
        payload = format_license(record)
        expires_at = parse_rfc3339(payload["license_expires_at"])
        remaining_time = split_remaining_time(now, expires_at)
        is_expired = now >= expires_at
        is_effectively_disabled = record.status == "disabled" or is_expired

        payload["remaining_time"] = remaining_time
        payload["remaining_time_label"] = format_remaining_time(remaining_time)
        payload["is_expired"] = is_expired
        payload["display_status"] = "disabled" if is_effectively_disabled else "active"
        payload["action_mode"] = "enable" if is_effectively_disabled else "disable"
        payload["requires_duration"] = is_expired
        payload["disable_action"] = str(
            request.url_for("admin_disable_license", license_key=record.license_key)
        )
        payload["enable_action"] = str(
            request.url_for("admin_enable_license", license_key=record.license_key)
        )
        rows.append(payload)

    return rows


@router.get("", response_class=HTMLResponse, name="admin_dashboard")
def dashboard(
    request: Request,
    _: str = Depends(_require_admin),
    message: str | None = None,
    error: str | None = None,
    key: str | None = None,
) -> HTMLResponse:
    settings = get_settings()
    init_db(settings.db_path)
    rows = _build_license_rows(request, settings.db_path)

    return templates.TemplateResponse(
        request=request,
        name="admin/index.html",
        context={
            "licenses": rows,
            "message": message,
            "error": error,
            "generated_key": key or "",
            "create_action": str(request.url_for("admin_create_license")),
            "generate_key_action": str(request.url_for("admin_generate_key")),
            "token_ttl_seconds": settings.token_ttl_seconds,
            "db_path": settings.db_path,
        },
    )


@router.get("/licenses", name="admin_list_licenses")
def list_licenses_view(
    request: Request,
    _: str = Depends(_require_admin),
) -> dict[str, Any]:
    settings = get_settings()
    init_db(settings.db_path)
    rows = _build_license_rows(request, settings.db_path)
    return {"licenses": rows, "total": len(rows)}


@router.post("/licenses", name="admin_create_license")
async def create_license_view(
    request: Request,
    _: str = Depends(_require_admin),
) -> RedirectResponse:
    settings = get_settings()
    init_db(settings.db_path)

    form = await request.form()

    days_raw = str(form.get("days", "")).strip()
    key_raw = str(form.get("key", "")).strip()
    note_raw = str(form.get("note", "")).strip()

    try:
        days = int(days_raw)
    except ValueError:
        return _redirect_to_dashboard(request, error="Days must be an integer.")

    key = key_raw or None
    note = note_raw or None

    try:
        record = create_license(
            settings.db_path,
            days=days,
            key=key,
            note=note,
        )
    except ValueError as exc:
        return _redirect_to_dashboard(request, error=str(exc))
    except sqlite3.IntegrityError:
        return _redirect_to_dashboard(request, error=f"License key already exists: {key}")
    except RuntimeError as exc:
        return _redirect_to_dashboard(request, error=str(exc))

    return _redirect_to_dashboard(request, message=f"License created: {record.license_key}")


@router.post("/licenses/{license_key}/disable", name="admin_disable_license")
def disable_license_view(
    request: Request,
    license_key: str,
    _: str = Depends(_require_admin),
) -> RedirectResponse:
    settings = get_settings()
    init_db(settings.db_path)

    if not disable_license(settings.db_path, license_key):
        return _redirect_to_dashboard(request, error=f"License key not found: {license_key}")

    return _redirect_to_dashboard(request, message=f"License disabled: {license_key}")


@router.post("/licenses/{license_key}/enable", name="admin_enable_license")
def enable_license_view(
    request: Request,
    license_key: str,
    days: str | None = Form(default=None),
    _: str = Depends(_require_admin),
) -> RedirectResponse:
    settings = get_settings()
    init_db(settings.db_path)

    record = get_license(settings.db_path, license_key)
    if record is None:
        return _redirect_to_dashboard(request, error=f"License key not found: {license_key}")

    now = utc_now()
    issued_at = parse_rfc3339(record.issued_at)
    is_expired = now >= issued_at + timedelta(days=record.duration_days)

    if is_expired:
        days_raw = (days or "").strip()
        if not days_raw:
            return _redirect_to_dashboard(
                request,
                error=f"License is expired. Select a duration (days) before enabling: {license_key}",
            )

        try:
            duration_days = int(days_raw)
        except ValueError:
            return _redirect_to_dashboard(request, error="Days must be an integer.")

        if duration_days < 1:
            return _redirect_to_dashboard(request, error="Days must be >= 1.")

        if not reactivate_license(
            settings.db_path,
            license_key,
            issued_at=to_rfc3339(now),
            duration_days=duration_days,
        ):
            return _redirect_to_dashboard(request, error=f"License key not found: {license_key}")

        return _redirect_to_dashboard(
            request,
            message=f"License reactivated for {duration_days} day(s): {license_key}",
        )

    if not enable_license(settings.db_path, license_key):
        return _redirect_to_dashboard(request, error=f"License key not found: {license_key}")

    return _redirect_to_dashboard(request, message=f"License enabled: {license_key}")


@router.post("/licenses/generate-key", name="admin_generate_key")
def generate_key_view(
    request: Request,
    _: str = Depends(_require_admin),
) -> RedirectResponse:
    settings = get_settings()
    init_db(settings.db_path)
    key = generate_unique_key(settings.db_path)
    return _redirect_to_dashboard_with_key(request, key)


def _redirect_to_dashboard_with_key(request: Request, key: str) -> RedirectResponse:
    base_url = str(request.url_for("admin_dashboard"))
    query = urlencode({"key": key, "message": "License key generated."})
    return RedirectResponse(url=f"{base_url}?{query}", status_code=status.HTTP_303_SEE_OTHER)
