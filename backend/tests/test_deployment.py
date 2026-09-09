import re
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.main import app

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def test_dockerfile_structure_and_multistage() -> None:
    """Verify Dockerfile exists, implements multi-stage build, and dynamic PORT."""
    dockerfile_path = REPO_ROOT / "Dockerfile"
    assert dockerfile_path.exists(), "Dockerfile must exist at repository root"

    content = dockerfile_path.read_text(encoding="utf-8")

    # Multi-stage build check (at least 2 FROM instructions)
    from_matches = re.findall(r"^FROM\s+([^\s]+)", content, flags=re.MULTILINE)
    assert (
        len(from_matches) >= 2
    ), f"Expected multi-stage Dockerfile (>= 2 FROMs), got: {from_matches}"
    for image in from_matches:
        assert "python:3.12" in image, f"Expected python:3.12 base image, got: {image}"

    # Non-root user check
    assert re.search(
        r"useradd|adduser", content, re.IGNORECASE
    ), "Must create a dedicated non-root user"
    assert re.search(
        r"USER\s+\w+", content
    ), "Must specify non-root USER instruction for runtime"

    # Application components copied
    assert "backend" in content, "Dockerfile must copy backend/ directory"
    assert "prompts" in content, "Dockerfile must copy prompts/ directory"
    assert "alembic" in content, "Dockerfile must copy alembic files for migrations"

    # Cloud Run dynamic PORT support
    assert re.search(
        r"\$\{?PORT(?::-8080)?\}?", content
    ), "Must dynamically bind to Cloud Run ${PORT}"


def test_dockerignore_configuration() -> None:
    """Verify .dockerignore excludes repository bloat and sensitive artifacts."""
    dockerignore_path = REPO_ROOT / ".dockerignore"
    assert dockerignore_path.exists(), ".dockerignore must exist at repository root"

    content = dockerignore_path.read_text(encoding="utf-8")
    lines = {
        line.strip()
        for line in content.splitlines()
        if line.strip() and not line.startswith("#")
    }

    expected_ignores = {".git", ".venv", "frontend", "__pycache__"}
    for item in expected_ignores:
        assert any(
            item in pattern for pattern in lines
        ), f"Expected {item} to be ignored in .dockerignore"


def test_readme_architecture_and_content_completeness() -> None:
    """Verify README.md contains all required sections from PRD §7."""
    readme_path = REPO_ROOT / "README.md"
    assert readme_path.exists(), "README.md must exist at repository root"

    content = readme_path.read_text(encoding="utf-8")

    # Architecture diagram
    assert "```mermaid" in content, "README must contain a Mermaid architecture diagram"
    assert "Next.js" in content or "Frontend" in content
    assert "FastAPI" in content or "Cloud Run" in content
    assert "Supabase" in content or "Postgres" in content

    # Five ADRs from PRD §7
    assert (
        "Postgres over Firestore" in content
    ), "Missing ADR 1: Postgres over Firestore"
    has_citations_adr = "Citations in data" in content or "Citations in Data" in content
    assert has_citations_adr, "Missing ADR 2: Citations in data"
    has_stages_adr = (
        "Three distinct LLM stages" in content or "Three Distinct LLM Stages" in content
    )
    assert has_stages_adr, "Missing ADR 3: Three LLM stages"
    assert (
        "watchdog" in content.lower()
    ), "Missing ADR 4: In-process background pipeline / watchdog"
    has_posting_adr = (
        "posting apis deferred" in content.lower() or "posting apis" in content.lower()
    )
    assert has_posting_adr, "Missing ADR 5: Posting APIs deferred"

    # Eval results table
    assert "RESULTS.md" in content or "Evaluation Results" in content
    assert "gemini-3.5-flash-lite" in content or "Extraction Accuracy" in content
    assert (
        "100.0%" in content or "100%" in content
    ), "README must show 100% bait-catch rate from evals"

    # Measured cost per kit from llm_calls
    assert (
        "SELECT" in content and "FROM llm_calls" in content
    ), "README must include the SQL query for measured cost"
    assert "prompt_tokens" in content and "completion_tokens" in content

    # Limitations & Roadmap
    assert "Limitations" in content, "README must document limitations"
    assert "Roadmap" in content, "README must document roadmap (v1.1+)"

    # Setup instructions
    assert "Setup" in content or "Getting Started" in content
    assert (
        "gcloud run deploy" in content
    ), "README must include Cloud Run deployment command"


def test_healthz_endpoint_contract() -> None:
    """Verify /healthz contract for Cloud Run health checking."""
    client = TestClient(app)

    with patch("backend.app.main.check_db_connection", return_value=True):
        resp = client.get("/healthz")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok", "db": "ok"}

    with patch("backend.app.main.check_db_connection", return_value=False):
        resp = client.get("/healthz")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok", "db": "down"}
