import copy
import os
import time
from typing import Any

import httpx

from backend.app.llm.client import LLMClient, LLMResponse, M

DEFAULT_GEMINI_MODEL = "gemini-3.5-flash-lite"
GEMINI_API_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"


def _inline_defs(schema: dict[str, Any]) -> dict[str, Any]:
    """Inline $defs and $ref into a self-contained schema for Gemini API."""
    defs = schema.get("$defs", {})

    def resolve(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                ref_name = str(node["$ref"]).split("/")[-1]
                return resolve(copy.deepcopy(defs.get(ref_name, {})))
            return {k: resolve(v) for k, v in node.items() if k != "$defs"}
        if isinstance(node, list):
            return [resolve(item) for item in node]
        return node

    resolved = resolve(schema)
    return resolved if isinstance(resolved, dict) else schema


class GeminiLLMClient(LLMClient):
    """Google Gemini LLM client implementing the LLMClient interface via REST API."""

    def __init__(
        self,
        api_key: str | None = None,
        model_id: str | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        key = api_key or os.getenv("GEMINI_API_KEY")
        if not key:
            raise ValueError("GEMINI_API_KEY environment variable is required")
        self.api_key = key
        self.model_id = model_id or os.getenv("GEMINI_MODEL") or DEFAULT_GEMINI_MODEL
        self._http_client = http_client or httpx.AsyncClient(timeout=60.0)

    async def _post_generate(
        self,
        contents: list[dict[str, Any]],
        system_instruction: str | None = None,
        temperature: float = 0.0,
        response_schema: dict[str, Any] | None = None,
    ) -> tuple[str, dict[str, Any], int]:
        url = f"{GEMINI_API_BASE_URL}/{self.model_id}:generateContent"

        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
            },
        }

        if system_instruction:
            payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}

        if response_schema:
            payload["generationConfig"]["responseMimeType"] = "application/json"
            payload["generationConfig"]["responseSchema"] = response_schema

        start_time = time.perf_counter()
        response = await self._http_client.send(
            self._http_client.build_request(
                "POST",
                url,
                params={"key": self.api_key},
                json=payload,
            )
        )
        latency_ms = int((time.perf_counter() - start_time) * 1000)

        response.raise_for_status()
        data = response.json()

        # Extract completion text
        candidates = data.get("candidates", [])
        if not candidates:
            raise ValueError("Gemini returned empty candidates")

        parts = candidates[0].get("content", {}).get("parts", [])
        text_content = "".join(part.get("text", "") for part in parts)
        usage = data.get("usageMetadata", {})

        return text_content, usage, latency_ms

    async def complete(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.0,
    ) -> LLMResponse[str]:
        contents = [{"parts": [{"text": prompt}]}]
        text, usage, latency_ms = await self._post_generate(
            contents=contents,
            system_instruction=system_prompt,
            temperature=temperature,
        )

        return LLMResponse[str](
            content=text,
            raw_text=text,
            model_id=self.model_id,
            prompt_tokens=usage.get("promptTokenCount", 0),
            completion_tokens=usage.get("candidatesTokenCount", 0),
            latency_ms=latency_ms,
        )

    async def complete_structured(
        self,
        prompt: str,
        response_model: type[M],
        system_prompt: str | None = None,
        temperature: float = 0.0,
    ) -> LLMResponse[M]:
        schema = _inline_defs(response_model.model_json_schema())
        contents = [{"parts": [{"text": prompt}]}]

        text, usage, latency_ms = await self._post_generate(
            contents=contents,
            system_instruction=system_prompt,
            temperature=temperature,
            response_schema=schema,
        )

        parsed_model = response_model.model_validate_json(text)

        return LLMResponse[M](
            content=parsed_model,
            raw_text=text,
            model_id=self.model_id,
            prompt_tokens=usage.get("promptTokenCount", 0),
            completion_tokens=usage.get("candidatesTokenCount", 0),
            latency_ms=latency_ms,
        )
