from datetime import datetime
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class SourceQuery(StrictModel):
    category: str = Field(min_length=1, max_length=64)
    text: str = Field(default="", max_length=500)


class ListingSummary(StrictModel):
    source: str = Field(min_length=1, max_length=64)
    external_id: str = Field(min_length=1, max_length=200)
    category: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=500)
    original_url: HttpUrl
    price_minor: int | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    region: str | None = Field(default=None, max_length=100)
    published_at: datetime | None = None
    fields: dict[str, Any] = Field(default_factory=dict)
    main_photo: str | None = None

    @model_validator(mode="after")
    def validate_price(self):
        if (self.price_minor is None) != (self.currency is None):
            raise ValueError("price_minor and currency must be supplied together")
        if self.published_at is not None and self.published_at.utcoffset() is None:
            raise ValueError("published_at must include a timezone")
        return self


class Listing(ListingSummary):
    description: str = Field(default="", max_length=10000)
    photos: list[str] = Field(default_factory=list, max_length=10)


class SourceMetadata(StrictModel):
    key: str
    name: str
    categories: tuple[str, ...]
    version: str = "1"
    allowed_hosts: tuple[str, ...] = ()
    min_request_interval_seconds: float = Field(default=10.0, ge=10.0, allow_inf_nan=False)
    max_concurrency: Literal[1] = 1
    external: bool = True


class SourceAdapter(Protocol):
    metadata: SourceMetadata

    async def search(self, query: SourceQuery) -> list[ListingSummary]: ...

    async def fetch_details(self, listing_id: str) -> Listing: ...


class RuleResult(StrictModel):
    status: Literal["passed", "rejected", "deferred"]
    reasons: list[str] = Field(default_factory=list)


class Category(Protocol):
    key: str
    prompt_template: str

    def field_schema(self) -> dict: ...

    def validate_fields(self, fields: dict) -> BaseModel: ...

    def validate_filters(self, filters: dict) -> BaseModel: ...

    def evaluate(self, listing: Listing, filters: BaseModel) -> RuleResult: ...

    def filter_schema(self) -> dict: ...