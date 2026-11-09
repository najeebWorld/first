import asyncio

import pytest
from pydantic import ValidationError

from src.domain.categories.vehicles import VehicleCategory, VehicleFields, VehicleFilters
from src.domain.models.listing import Listing, SourceQuery


def vehicle_listing(**fields):
    return Listing(
        source="demo",
        external_id="vehicle-1",
        category="vehicles",
        title="Hyundai i20",
        original_url="https://demo.invalid/vehicles/1",
        price_minor=4_200_000,
        currency="ILS",
        region="center",
        fields={"make": "hyundai", "model": "i20", "year": 2020, "km": 70000, "hand": 1, **fields},
    )


def test_vehicle_rules_pass_before_any_ai():
    category = VehicleCategory()
    filters = category.validate_filters({"year_min": 2019, "km_max": 80000, "hand_max": 1, "price_max_minor": 4_500_000})
    assert category.evaluate(vehicle_listing(), filters).status == "passed"


@pytest.mark.parametrize("field,value", [("year", 2018), ("km", 90000), ("hand", 2)])
def test_vehicle_rules_reject_mismatch(field, value):
    category = VehicleCategory()
    filters = category.validate_filters({"year_min": 2019, "km_max": 80000, "hand_max": 1})
    assert category.evaluate(vehicle_listing(**{field: value}), filters).status == "rejected"


def test_missing_required_fact_is_deferred_not_a_pass():
    category = VehicleCategory()
    filters = category.validate_filters({"km_max": 80000})
    assert category.evaluate(vehicle_listing(km=None), filters).status == "deferred"


def test_filters_reject_invalid_ranges_unknown_fields_and_boolean_numbers():
    for filters in ({"year_min": 2021, "year_max": 2020}, {"unknown": True}, {"km_max": True}):
        with pytest.raises(ValidationError):
            VehicleFilters.model_validate(filters)
    with pytest.raises(ValidationError):
        VehicleFields.model_validate({"hand": 0})


def test_listing_price_and_currency_are_paired():
    with pytest.raises(ValidationError):
        Listing.model_validate(vehicle_listing().model_dump() | {"currency": None})


def test_query_rejects_customer_identifiers():
    with pytest.raises(ValidationError):
        SourceQuery.model_validate({"category": "vehicles", "user_id": "another-user"})


def test_demo_appears_over_time_without_network(monkeypatch):
    import socket
    from src.infrastructure.sources.demo import DemoAdapter

    def forbid_network(*args, **kwargs):
        raise AssertionError("demo must not use a network")

    monkeypatch.setattr(socket, "create_connection", forbid_network)
    current_time = [1000.0]
    adapter = DemoAdapter(epoch=1000.0, clock=lambda: current_time[0])
    query = SourceQuery(category="vehicles")
    initial = asyncio.run(adapter.search(query))
    assert len(initial) == 2
    with pytest.raises(LookupError):
        asyncio.run(adapter.fetch_details("demo-003"))
    current_time[0] += 120
    later = asyncio.run(adapter.search(query))
    assert len(later) == 4
    assert {item.external_id for item in initial} < {item.external_id for item in later}
    detail = asyncio.run(adapter.fetch_details("demo-003"))
    assert detail.fields["make"] == "hyundai"
    assert detail.original_url.host == "demo.invalid"
    assert detail.photos == ["/static/demo/vehicle-placeholder.svg"]
    detail.fields["make"] = "changed"
    assert asyncio.run(adapter.fetch_details("demo-003")).fields["make"] == "hyundai"


def test_demo_query_and_generic_scan():
    from src.infrastructure.sources.demo import DemoAdapter
    from src.services.source_scan_service import SourceScanService

    adapter = DemoAdapter(epoch=0.0, clock=lambda: 120.0)
    service = SourceScanService(sources=[adapter], categories=[VehicleCategory()])
    results = asyncio.run(service.scan("demo", SourceQuery(category="vehicles", text="יונדאי"), {"km_max": 80000}))
    assert [result.listing.external_id for result in results] == ["demo-001", "demo-003", "demo-004"]
    assert [result.rule_result.status for result in results] == ["passed", "passed", "deferred"]


def test_unapproved_source_rejected_before_fetch():
    from src.domain.models.listing import SourceMetadata
    from src.infrastructure.sources.demo import DemoAdapter
    from src.services.source_scan_service import SourceScanService

    adapter = DemoAdapter(epoch=0.0, clock=lambda: 0.0)
    adapter.metadata = SourceMetadata(key="unapproved", name="Unapproved", categories=("vehicles",))
    async def unexpected(query):
        raise AssertionError("Unapproved adapter must not be invoked")
    adapter.search = unexpected
    service = SourceScanService(sources=[adapter], categories=[VehicleCategory()])
    with pytest.raises(PermissionError, match="not approved"):
        asyncio.run(service.scan("unapproved", SourceQuery(category="vehicles"), {}))


def test_new_category_does_not_require_core_changes():
    from src.domain.models.listing import RuleResult, SourceMetadata, StrictModel
    from src.services.source_scan_service import SourceScanService

    class TestFilters(StrictModel):
        pass

    class TestCategory:
        key = "test-category"
        prompt_template = "Test category"

        def validate_fields(self, fields):
            return TestFilters.model_validate(fields)

        def validate_filters(self, filters):
            return TestFilters.model_validate(filters)

        def evaluate(self, listing, filters):
            return RuleResult(status="passed")

        def filter_schema(self):
            return TestFilters.model_json_schema()

        def field_schema(self):
            return TestFilters.model_json_schema()

    class TestSource:
        metadata = SourceMetadata(key="fixture", name="Fixture", categories=("test-category",), external=False)

        async def search(self, query):
            return [await self.fetch_details("1")]

        async def fetch_details(self, listing_id):
            return Listing(source="fixture", external_id=listing_id, category="test-category", title="Fixture", original_url="https://demo.invalid/1")

    service = SourceScanService(sources=[TestSource()], categories=[TestCategory()])
    results = asyncio.run(service.scan("fixture", SourceQuery(category="test-category"), {}))
    assert results[0].rule_result.status == "passed"


@pytest.mark.parametrize("filters,status", [
    ({"include_keywords": ["HYUNDAI"]}, "passed"),
    ({"include_keywords": ["toyota"]}, "rejected"),
    ({"exclude_keywords": ["i20"]}, "rejected"),
    ({"make": " Hyundai ", "model": "I20"}, "passed"),
    ({"make": "toyota"}, "rejected"),
    ({"regions": ["north"]}, "rejected"),
    ({"seller_types": ["private"]}, "deferred"),
    ({"price_max_minor": 4_000_000}, "rejected"),
    ({"price_max_minor": 4_200_000}, "passed"),
    ({"price_max_minor": 4_200_000, "currency": "USD"}, "rejected"),
])
def test_vehicle_filter_variants(filters, status):
    category = VehicleCategory()
    assert category.evaluate(vehicle_listing(), category.validate_filters(filters)).status == status


def test_category_exposes_schemas_for_future_forms():
    category = VehicleCategory()
    assert "km" in category.field_schema()["properties"]
    assert "km_max" in category.filter_schema()["properties"]
    assert category.filter_schema()["additionalProperties"] is False


def test_demo_image_is_local_and_marked_fictional():
    from pathlib import Path
    from xml.etree import ElementTree

    image = Path(__file__).resolve().parents[2] / "static/demo/vehicle-placeholder.svg"
    root = ElementTree.parse(image).getroot()
    assert "FICTIONAL" in "".join(root.itertext())
    assert root.attrib["viewBox"] == "0 0 640 360"
    assert all("href" not in key for element in root.iter() for key in element.attrib)