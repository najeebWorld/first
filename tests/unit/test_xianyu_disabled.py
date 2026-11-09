import asyncio

import pytest

from src.domain.models.listing import SourceQuery
from src.infrastructure.sources.xianyu import XianyuAdapter


def test_xianyu_has_no_live_entry_point():
    adapter = XianyuAdapter()
    assert adapter.metadata.external
    with pytest.raises(PermissionError, match="disabled"):
        asyncio.run(adapter.search(SourceQuery(category="second_hand")))
    with pytest.raises(PermissionError, match="disabled"):
        asyncio.run(adapter.fetch_details("any-id"))


def test_app_does_not_register_marketplace_cookie_routes():
    from src.app import app

    assert not any(
        getattr(route, "path", "").startswith(("/api/accounts", "/api/login-state"))
        for route in app.routes
    )