from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Coverage Amplifier API", version="0.1.0")


class HealthResponse(BaseModel):
    status: str
    db: str


@app.get("/healthz", response_model=HealthResponse)
def healthz() -> dict[str, Any]:
    return {"status": "ok", "db": "unknown"}
