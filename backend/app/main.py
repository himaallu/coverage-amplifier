from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

from backend.app.api.kits import router as kits_router
from backend.app.db.session import check_db_connection

app = FastAPI(title="Coverage Amplifier API", version="0.1.0")
app.include_router(kits_router)


class HealthResponse(BaseModel):
    status: str
    db: str


@app.get("/healthz", response_model=HealthResponse)
def healthz() -> dict[str, Any]:
    db_ok = check_db_connection()
    return {"status": "ok", "db": "ok" if db_ok else "down"}
