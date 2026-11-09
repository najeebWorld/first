import asyncio
import math
import time
from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx
from pydantic import ConfigDict, Field, model_validator

from src.domain.models.listing import StrictModel


class SourceHttpPolicy(StrictModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    origin: str
    enabled: bool = False
    approval_reference: str = ""
    user_agent: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]*Bot/[0-9.]+$")
    contact_url: str
    min_request_interval_seconds: float = Field(default=10.0, ge=10, allow_inf_nan=False)
    robots_ttl_seconds: float = Field(default=3600.0, ge=60, le=86400, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_public_origin(self):
        origin = urlsplit(self.origin)
        contact = urlsplit(self.contact_url)
        for parsed in (origin, contact):
            if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError("Source and contact must be configured HTTPS URLs without credentials")
        if origin.path not in ("", "/") or origin.query or origin.fragment:
            raise ValueError("Source origin must not include a path, query or fragment")
        if any(char.isspace() or ord(char) < 32 for char in self.contact_url + self.origin):
            raise ValueError("URLs cannot contain whitespace or control characters")
        if self.enabled and not self.approval_reference.strip():
            raise ValueError("Enabled sources require a recorded approval reference")
        return self


class SourceHttpClient:
    """Single-worker policy transport. Live registration awaits durable worker state."""

    def __init__(
        self,
        policy: SourceHttpPolicy,
        *,
        transport: httpx.AsyncBaseTransport,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        self.policy = policy
        self.blocked_status: int | None = None
        self._clock = clock
        self._sleeper = sleeper
        self._lock = asyncio.Lock()
        self._last_request: float | None = None
        self._interval = policy.min_request_interval_seconds
        self._robots: RobotFileParser | None = None
        self._robots_expires = 0.0
        self._origin = httpx.URL(policy.origin)
        self._user_agent = f"{policy.user_agent} (+{policy.contact_url})"
        self._client = httpx.AsyncClient(
            transport=transport, follow_redirects=False, trust_env=False, timeout=15.0,
            headers={"User-Agent": self._user_agent},
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self._client.aclose()

    def _check_access(self, url: str) -> httpx.URL:
        if not self.policy.enabled or not self.policy.approval_reference.strip():
            raise PermissionError("Source is not approved and enabled")
        if self.blocked_status is not None:
            raise PermissionError(f"Source blocked after HTTP {self.blocked_status}; operator review required")
        target = httpx.URL(url)
        if (target.scheme, target.host, target.port) != (self._origin.scheme, self._origin.host, self._origin.port) or target.userinfo or target.fragment:
            raise PermissionError("URL is outside the approved origin")
        return target

    async def _request(self, url: httpx.URL) -> httpx.Response:
        self._check_access(str(url))
        if self._last_request is not None:
            delay = self._last_request + self._interval - self._clock()
            if delay > 0:
                await self._sleeper(delay)
        self._last_request = self._clock()
        self._client.cookies.clear()
        response = await self._client.get(url)
        self._client.cookies.clear()
        if response.status_code in (403, 429):
            self.blocked_status = response.status_code
            raise PermissionError(f"Source blocked after HTTP {response.status_code}; operator review required")
        return response

    async def _load_robots(self):
        robots_url = self._origin.copy_with(path="/robots.txt")
        response = await self._request(robots_url)
        lines = response.text.splitlines()
        if response.status_code != 200 or not any(line.strip().lower().startswith("user-agent:") for line in lines):
            raise PermissionError("Cannot verify robots policy; access denied")
        robots = RobotFileParser(str(robots_url))
        robots.parse(lines)
        interval = self.policy.min_request_interval_seconds
        crawl_delay = robots.crawl_delay(self._user_agent)
        request_rate = robots.request_rate(self._user_agent)
        if crawl_delay is not None:
            interval = max(interval, float(crawl_delay))
        if request_rate is not None:
            if request_rate.requests <= 0 or request_rate.seconds <= 0:
                raise PermissionError("Invalid robots request rate")
            interval = max(interval, request_rate.seconds / request_rate.requests)
        if not math.isfinite(interval):
            raise PermissionError("Invalid robots pacing policy")
        self._interval = interval
        self._robots = robots
        self._robots_expires = self._clock() + self.policy.robots_ttl_seconds

    async def get(self, url: str) -> httpx.Response:
        async with self._lock:
            target = self._check_access(url)
            if self._robots is None or self._clock() >= self._robots_expires:
                await self._load_robots()
            if not self._robots.can_fetch(self._user_agent, str(target)):
                raise PermissionError("URL denied by robots policy")
            response = await self._request(target)
            if response.is_redirect:
                raise PermissionError("Source redirects require separate origin and policy review")
            response.raise_for_status()
            return response