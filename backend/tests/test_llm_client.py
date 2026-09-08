import pytest
from pydantic import BaseModel

from backend.app.llm.client import LLMClient, LLMResponse, M


class SampleModel(BaseModel):
    title: str
    count: int


class MockConcreteClient(LLMClient):
    async def complete(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.0,
    ) -> LLMResponse[str]:
        return LLMResponse[str](
            content="Mock completion text",
            raw_text="Mock completion text",
            model_id="mock-model",
            prompt_tokens=10,
            completion_tokens=5,
            latency_ms=120,
        )

    async def complete_structured(
        self,
        prompt: str,
        response_model: type[M],
        system_prompt: str | None = None,
        temperature: float = 0.0,
    ) -> LLMResponse[M]:
        return LLMResponse[M](
            content=response_model.model_validate({"title": "Test", "count": 42}),
            raw_text='{"title": "Test", "count": 42}',
            model_id="mock-model",
            prompt_tokens=15,
            completion_tokens=8,
            latency_ms=180,
        )


def test_llm_client_cannot_be_instantiated_directly() -> None:
    with pytest.raises(TypeError, match="Can't instantiate abstract class"):
        LLMClient()  # type: ignore[abstract]


@pytest.mark.anyio
async def test_llm_client_subclass_fulfills_contract() -> None:
    client = MockConcreteClient()
    res = await client.complete("Hello")
    assert res.content == "Mock completion text"
    assert res.prompt_tokens == 10
    assert res.completion_tokens == 5
    assert res.latency_ms == 120
    assert res.model_id == "mock-model"

    structured_res = await client.complete_structured("Give me JSON", SampleModel)
    assert isinstance(structured_res.content, SampleModel)
    assert structured_res.content.title == "Test"
    assert structured_res.content.count == 42
