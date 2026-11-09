from src.domain.models.listing import Listing, ListingSummary, SourceMetadata, SourceQuery


DISABLED_REASON = "Xianyu is disabled: no approved public API/feed is configured. Legacy browser and cookie collection was removed."


class XianyuAdapter:
    metadata = SourceMetadata(key="xianyu", name="Xianyu (disabled)", categories=("second_hand",))

    async def search(self, query: SourceQuery) -> list[ListingSummary]:
        raise PermissionError(DISABLED_REASON)

    async def fetch_details(self, listing_id: str) -> Listing:
        raise PermissionError(DISABLED_REASON)