from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field


StatusType = Literal["active", "disabled"]
DeniedReason = Literal["not_found", "disabled", "expired"]


@dataclass(frozen=True)
class LicenseRecord:
    license_key: str
    issued_at: str
    duration_days: int
    status: StatusType
    note: str | None = None


class TokenRequest(BaseModel):
    license_key: str = Field(min_length=1)
    app_id: str | None = None
    app_version: str | None = None


class LeaseInfo(BaseModel):
    lease_id: str
    issued_at: str
    expires_at: str


class RemainingTimeInfo(BaseModel):
    years: int = Field(ge=0)
    months: int = Field(ge=0)
    days: int = Field(ge=0)
    hours: int = Field(ge=0)
    minutes: int = Field(ge=0)
    seconds: int = Field(ge=0)


class LicenseInfo(BaseModel):
    license_key: str = Field(min_length=1)
    issued_at: str
    duration_days: int = Field(ge=1)
    license_expires_at: str
    remaining_time: RemainingTimeInfo


class TokenAllowedResponse(BaseModel):
    allowed: Literal[True]
    lease: LeaseInfo
    license: LicenseInfo
    token_ttl_seconds: int = Field(ge=1)
    server_time: str


class TokenDeniedResponse(BaseModel):
    allowed: Literal[False]
    reason: DeniedReason
    server_time: str
