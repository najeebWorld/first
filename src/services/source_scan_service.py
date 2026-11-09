from collections.abc import Iterable

from src.domain.models.listing import Category, Listing, RuleResult, SourceAdapter, SourceQuery, StrictModel


class ScanResult(StrictModel):
    listing: Listing
    rule_result: RuleResult


class SourceScanService:
    def __init__(
        self,
        *,
        sources: Iterable[SourceAdapter],
        categories: Iterable[Category],
    ):
        self._sources = {}
        self._categories = {}
        for source in sources:
            if source.metadata.key in self._sources:
                raise ValueError("Duplicate source key")
            self._sources[source.metadata.key] = source
        for category in categories:
            if category.key in self._categories:
                raise ValueError("Duplicate category key")
            self._categories[category.key] = category

    async def scan(self, source_key: str, query: SourceQuery, filters: dict) -> list[ScanResult]:
        if source_key not in self._sources:
            raise PermissionError(f"Source {source_key!r} is not approved or installed")
        source = self._sources[source_key]
        if source.metadata.external:
            raise PermissionError(f"Source {source_key!r} is not approved; live registration awaits durable source policy")
        if query.category not in source.metadata.categories or query.category not in self._categories:
            raise ValueError("Unsupported category")
        category = self._categories[query.category]
        validated_filters = category.validate_filters(filters)
        results = []
        seen = set()
        for summary in await source.search(query):
            if summary.source != source_key or summary.category != query.category:
                raise ValueError("Source returned inconsistent listing metadata")
            if summary.external_id in seen:
                continue
            seen.add(summary.external_id)
            listing = await source.fetch_details(summary.external_id)
            if (listing.source, listing.category, listing.external_id) != (source_key, query.category, summary.external_id):
                raise ValueError("Source returned details for another listing")
            category.validate_fields(listing.fields)
            results.append(ScanResult(listing=listing, rule_result=category.evaluate(listing, validated_filters)))
        return results