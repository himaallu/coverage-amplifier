import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from pydantic import BaseModel

from backend.app.llm.client import LLMClient
from backend.app.llm.gemini import GeminiLLMClient


class SampleResponseModel(BaseModel):
    summary: str
    count: int


def test_gemini_client_inherits_llm_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")
    client = GeminiLLMClient()
    assert isinstance(client, LLMClient)


def test_gemini_client_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(
        ValueError, match="GEMINI_API_KEY environment variable is required"
    ):
        GeminiLLMClient()


@pytest.mark.anyio
async def test_gemini_client_complete(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")
    client = GeminiLLMClient()

    mock_gemini_payload = {
        "candidates": [
            {
                "content": {"parts": [{"text": "Hello from Gemini"}]},
                "finishReason": "STOP",
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 20,
            "candidatesTokenCount": 10,
            "totalTokenCount": 30,
        },
    }

    mock_response = httpx.Response(
        status_code=200,
        json=mock_gemini_payload,
        request=httpx.Request("POST", "https://generativelanguage.googleapis.com"),
    )

    with patch.object(client._http_client, "send", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = mock_response
        resp = await client.complete("Say hello")
        assert resp.content == "Hello from Gemini"
        assert resp.prompt_tokens == 20
        assert resp.completion_tokens == 10
        assert resp.latency_ms >= 0


@pytest.mark.anyio
async def test_gemini_client_complete_structured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")
    client = GeminiLLMClient()

    mock_gemini_payload = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"text": json.dumps({"summary": "Tech news", "count": 5})}
                    ]
                },
                "finishReason": "STOP",
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 30,
            "candidatesTokenCount": 15,
            "totalTokenCount": 45,
        },
    }

    mock_response = httpx.Response(
        status_code=200,
        json=mock_gemini_payload,
        request=httpx.Request("POST", "https://generativelanguage.googleapis.com"),
    )

    with patch.object(client._http_client, "send", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = mock_response
        resp = await client.complete_structured(
            "Extract structured data", SampleResponseModel
        )
        assert isinstance(resp.content, SampleResponseModel)
        assert resp.content.summary == "Tech news"
        assert resp.content.count == 5
