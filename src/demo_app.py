from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from src.domain.categories.vehicles import VehicleCategory, VehicleFilters
from src.domain.models.listing import SourceQuery, StrictModel
from src.infrastructure.sources.demo import DemoAdapter
from src.services.source_scan_service import ScanResult, SourceScanService


class DemoScanRequest(StrictModel):
    elapsed_seconds: int = Field(default=120, ge=0, le=120)
    text: str = Field(default="", max_length=500)
    filters: VehicleFilters = Field(default_factory=VehicleFilters)


class DemoScanResponse(StrictModel):
    results: list[ScanResult]


app = FastAPI(title="Local Vehicle Demo", docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]"])


@app.middleware("http")
async def local_origin_only(request: Request, call_next):
    origin = request.headers.get("origin")
    if origin:
        try:
            parsed = urlsplit(origin)
            allowed = parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        except ValueError:
            allowed = False
        if not allowed:
            return JSONResponse({"detail": "Local demo origins only"}, status_code=403)
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.post("/demo-api/scan", response_model=DemoScanResponse)
async def scan_demo(payload: DemoScanRequest):
    service = SourceScanService(
        sources=[DemoAdapter(epoch=0.0, clock=lambda: float(payload.elapsed_seconds))],
        categories=[VehicleCategory()],
    )
    results = await service.scan("demo", SourceQuery(category="vehicles", text=payload.text), payload.filters.model_dump())
    return DemoScanResponse(results=results)


root = Path(__file__).resolve().parents[1]
app.mount("/static/demo", StaticFiles(directory=root / "static/demo"), name="demo-images")