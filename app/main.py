from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.db import init_db
from app.models import TokenAllowedResponse, TokenDeniedResponse, TokenRequest
from app.service import issue_token
from app.settings import get_settings
from app.web_admin import router as admin_router

BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    init_db(settings.db_path)
    yield


app = FastAPI(title="CCM License Server MVP", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
app.include_router(admin_router)


@app.post("/v1/token", response_model=TokenAllowedResponse | TokenDeniedResponse)
def create_token(request: TokenRequest) -> TokenAllowedResponse | TokenDeniedResponse:
    settings = get_settings()
    return issue_token(
        db_path=settings.db_path,
        token_ttl_seconds=settings.token_ttl_seconds,
        license_key=request.license_key,
        app_id=request.app_id,
        app_version=request.app_version,
    )


if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )
