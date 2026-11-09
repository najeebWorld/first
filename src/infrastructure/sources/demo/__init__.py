import time
from collections.abc import Callable
from pathlib import Path

from pydantic import Field, TypeAdapter

from src.domain.models.listing import Listing, ListingSummary, SourceMetadata, SourceQuery, StrictModel


class DemoEntry(StrictModel):
    available_after_seconds: int = Field(ge=0)
    listing: Listing


class DemoAdapter:
    metadata = SourceMetadata(
        key="demo", name="מודעות רכב פיקטיביות", categories=("vehicles",),
        allowed_hosts=("demo.invalid",), external=False
    )

    def __init__(
        self,
        *,
        epoch: float | None = None,
        clock: Callable[[], float] = time.time,
        fixture_path: Path | None = None,
    ):
        self._clock = clock
        self._epoch = clock() if epoch is None else epoch
        path = fixture_path or Path(__file__).with_name("vehicles.json")
        self._entries = TypeAdapter(list[DemoEntry]).validate_json(path.read_text(encoding="utf-8"))
        identifiers = [entry.listing.external_id for entry in self._entries]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("Duplicate demo listing IDs")
        for entry in self._entries:
            if entry.listing.source != self.metadata.key or entry.listing.original_url.host != "demo.invalid":
                raise ValueError("Demo fixtures must use the demo source and reserved demo.invalid host")
            entry.listing.main_photo = "/static/demo/vehicle-placeholder.svg"
            entry.listing.photos = [entry.listing.main_photo]

    def _available(self) -> list[Listing]:
        elapsed = self._clock() - self._epoch
        return [entry.listing for entry in self._entries if entry.available_after_seconds <= elapsed]

    async def search(self, query: SourceQuery) -> list[ListingSummary]:
        if query.category not in self.metadata.categories:
            raise ValueError("Unsupported source category")
        terms = query.text.casefold().split()
        results = []
        for listing in self._available():
            text = f"{listing.title} {listing.description}".casefold()
            if all(term in text for term in terms):
                results.append(ListingSummary.model_validate(listing.model_dump(exclude={"description", "photos"})))
        return results

    async def fetch_details(self, listing_id: str) -> Listing:
        for listing in self._available():
            if listing.external_id == listing_id:
                return listing.model_copy(deep=True)
        raise LookupError("Demo listing is not available")