import asyncio

import httpx
import pytest

from src.infrastructure.sources.http import SourceHttpClient, SourceHttpPolicy


def make_policy(**changes):
    values = dict(origin="https://source.invalid", enabled=True, approval_reference="owner-approved-test-feed",
                  user_agent="DealAlertsBot/0.1", contact_url="https://operator.invalid/contact")
    return SourceHttpPolicy(**(values | changes))


def test_unapproved_source_never_sends_request():
    async def scenario():
        def unexpected(request):
            raise AssertionError("Network must not be used")

        async with SourceHttpClient(make_policy(enabled=False), transport=httpx.MockTransport(unexpected)) as client:
            with pytest.raises(PermissionError, match="approved"):
                await client.get("https://source.invalid/listings")

    asyncio.run(scenario())


def test_robots_and_rate_limit_cover_every_request():
    async def scenario():
        now = [0.0]
        requests = []

        async def advance(seconds):
            now[0] += seconds

        def response(request):
            requests.append((str(request.url), now[0], request.headers["user-agent"]))
            text = "User-agent: *\nDisallow: /private\nCrawl-delay: 15\n" if request.url.path == "/robots.txt" else "ok"
            return httpx.Response(200, text=text)

        async with SourceHttpClient(make_policy(), transport=httpx.MockTransport(response), clock=lambda: now[0], sleeper=advance) as client:
            await asyncio.gather(client.get("https://source.invalid/listings"), client.get("https://source.invalid/details/1"))
            with pytest.raises(PermissionError, match="robots"):
                await client.get("https://source.invalid/private")
            with pytest.raises(PermissionError, match="origin"):
                await client.get("https://another.invalid/listings")
        assert [timestamp for _, timestamp, _ in requests] == [0.0, 15.0, 30.0]
        assert all(agent == "DealAlertsBot/0.1 (+https://operator.invalid/contact)" for _, _, agent in requests)

    asyncio.run(scenario())


@pytest.mark.parametrize("status", [403, 429])
@pytest.mark.parametrize("on_robots", [False, True])
def test_source_stays_blocked_after_denial(status, on_robots):
    async def scenario():
        requests = []

        async def no_wait(seconds):
            pass

        def response(request):
            requests.append(request.url.path)
            if request.url.path == "/robots.txt" and not on_robots:
                return httpx.Response(200, text="User-agent: *\nAllow: /\n")
            return httpx.Response(status)

        async with SourceHttpClient(make_policy(), transport=httpx.MockTransport(response), sleeper=no_wait) as client:
            with pytest.raises(PermissionError, match="blocked"):
                await client.get("https://source.invalid/listings")
            request_count = len(requests)
            with pytest.raises(PermissionError, match="blocked"):
                await client.get("https://source.invalid/details/1")
            assert len(requests) == request_count
            assert client.blocked_status == status

    asyncio.run(scenario())


@pytest.mark.parametrize("status", [302, 404, 500])
def test_unavailable_robots_fails_closed(status):
    async def scenario():
        requests = []

        def response(request):
            requests.append(request.url.path)
            return httpx.Response(status, headers={"Location": "https://another.invalid/"})

        async with SourceHttpClient(make_policy(), transport=httpx.MockTransport(response)) as client:
            with pytest.raises(PermissionError, match="robots"):
                await client.get("https://source.invalid/listings")
        assert requests == ["/robots.txt"]

    asyncio.run(scenario())