import os
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.app.api.kits import router as kits_router
from backend.app.db.session import check_db_connection

app = FastAPI(title="Coverage Amplifier API", version="0.1.0")

# CORS locked to Vercel origin and local frontend
allowed_origins_env = os.getenv("ALLOWED_ORIGINS")
if allowed_origins_env:
    allowed_origins = [
        orig.strip() for orig in allowed_origins_env.split(",") if orig.strip()
    ]
else:
    allowed_origins = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://*.vercel.app",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=r"https://.*\.vercel\.app"
    if "https://*.vercel.app" in allowed_origins
    else None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(kits_router)


class HealthResponse(BaseModel):
    status: str
    db: str


@app.get("/healthz", response_model=HealthResponse)
@app.get("/health", response_model=HealthResponse)
@app.get("/api/healthz", response_model=HealthResponse)
def healthz() -> dict[str, Any]:
    db_ok = check_db_connection()
    return {"status": "ok", "db": "ok" if db_ok else "down"}
