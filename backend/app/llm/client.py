from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")
M = TypeVar("M", bound=BaseModel)


class LLMResponse(BaseModel, Generic[T]):
    content: T
    raw_text: str
    model_id: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int


class LLMClient(ABC):
    @abstractmethod
    async def complete(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.0,
    ) -> LLMResponse[str]:
        """Execute a text completion prompt."""
        ...

    @abstractmethod
    async def complete_structured(
        self,
        prompt: str,
        response_model: type[M],
        system_prompt: str | None = None,
        temperature: float = 0.0,
    ) -> LLMResponse[M]:
        """Execute a structured completion returning a validated Pydantic model."""
        ...
