from fastapi.testclient import TestClient

from src.demo_app import app


def test_demo_api_filters_and_exposes_only_fictional_listings():
    with TestClient(app, base_url="http://localhost") as client:
        response = client.post("/demo-api/scan", json={"elapsed_seconds": 120, "text": "יונדאי", "filters": {"km_max": 80000}})
    assert response.status_code == 200
    payload = response.json()
    assert [item["rule_result"]["status"] for item in payload["results"]] == ["passed", "passed", "deferred"]
    assert all("demo.invalid" in item["listing"]["original_url"] for item in payload["results"])


def test_demo_api_validates_filters_and_time():
    with TestClient(app, base_url="http://localhost") as client:
        for payload in ({"elapsed_seconds": -1}, {"filters": {"km_max": True}}, {"filters": {"year_min": 2022, "year_max": 2019}}, {"source": "yad2"}):
            assert client.post("/demo-api/scan", json=payload).status_code == 422


def test_demo_api_initial_clock_and_local_asset():
    with TestClient(app, base_url="http://localhost") as client:
        assert len(client.post("/demo-api/scan", json={"elapsed_seconds": 0}).json()["results"]) == 2
        response = client.get("/static/demo/vehicle-placeholder.svg")
        assert response.status_code == 200
        assert "FICTIONAL" in response.text
        assert client.get("/api/settings").status_code == 404
        assert client.post("/api/login-state", json={"content": "{}"}).status_code == 404


def test_demo_api_rejects_foreign_host_and_origin():
    with TestClient(app, base_url="http://localhost") as client:
        assert client.post("/demo-api/scan", json={}, headers={"Origin": "https://untrusted.invalid"}).status_code == 403
        assert client.post("/demo-api/scan", json={}, headers={"Host": "untrusted.invalid"}).status_code == 400