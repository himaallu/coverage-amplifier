from pydantic import BaseModel, Field, field_validator, model_validator


class SourceSentence(BaseModel):
    id: str = Field(
        ...,
        pattern=r"^S\d+$",
        description="Unique identifier S1, S2, etc.",
    )
    text: str = Field(
        ...,
        min_length=5,
        description="Verbatim source sentence quote",
    )


class ExtractionOutput(BaseModel):
    title: str = Field(..., min_length=1, description="Article title")
    outlet: str = Field(..., min_length=1, description="News outlet or publisher")
    author: str | None = Field(default=None, description="Article author")
    published_at: str | None = Field(default=None, description="Publication date")
    source_sentences: list[SourceSentence] = Field(
        ...,
        min_length=8,
        max_length=20,
        description="List of 8 to 20 atomic, verbatim source sentences",
    )

    @field_validator("source_sentences")
    @classmethod
    def validate_sentence_count(cls, v: list[SourceSentence]) -> list[SourceSentence]:
        if len(v) < 8 or len(v) > 20:
            raise ValueError(f"Sentence count must be between 8 and 20, got {len(v)}")
        return v

    @model_validator(mode="after")
    def validate_unique_sentence_ids(self) -> "ExtractionOutput":
        seen_ids: set[str] = set()
        for sentence in self.source_sentences:
            if sentence.id in seen_ids:
                raise ValueError(
                    f"Sentence IDs must be unique: duplicate ID '{sentence.id}'"
                )
            seen_ids.add(sentence.id)
        return self
