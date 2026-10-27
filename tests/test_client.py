"""Tests for RemonClient against a real local HTTP server."""

from __future__ import annotations

import asyncio
import socket
from collections.abc import Awaitable, Callable

import aiohttp
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from remon_home_integration import (
    STATUS_PATH,
    RemonClient,
    RemonConnectionError,
    RemonResponseError,
    RemonStatus,
    RemonUnsupportedApiError,
)

from .conftest import load_fixture

Handler = Callable[[web.Request], Awaitable[web.StreamResponse]]
ServerFactory = Callable[[Handler], Awaitable[TestServer]]


@pytest.fixture
def device(aiohttp_server: Callable[..., Awaitable[TestServer]]) -> ServerFactory:
    """Start a fake device whose /api/status is served by ``handler``."""

    async def start(handler: Handler) -> TestServer:
        app = web.Application()
        app.router.add_get(STATUS_PATH, handler)
        return await aiohttp_server(app)

    return start


def body(raw: bytes, status: int = 200) -> Handler:
    async def handler(_: web.Request) -> web.Response:
        return web.Response(body=raw, status=status, content_type="application/json")

    return handler


def client_for(server: TestServer, session: aiohttp.ClientSession, **kwargs: float) -> RemonClient:
    assert server.port is not None
    return RemonClient(server.host, session, port=server.port, **kwargs)


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port: int = sock.getsockname()[1]
        return port


# --- happy path -----------------------------------------------------------------------------


async def test_get_status(device: ServerFactory) -> None:
    server = await device(body(load_fixture("saltbuddy.json")))
    async with aiohttp.ClientSession() as session:
        status = await client_for(server, session).get_status()
    assert status == RemonStatus(
        id="SaltBuddy-a1b2c3d4e5f6",
        type="SaltBuddy",
        fw="382de8e",
        salt_level=64,
        sensor_error=False,
        leak=False,
    )


async def test_null_salt_level(device: ServerFactory) -> None:
    server = await device(body(load_fixture("softener_no_sample.json")))
    async with aiohttp.ClientSession() as session:
        status = await client_for(server, session).get_status()
    assert status.salt_level is None
    assert status.sensor_error is True


async def test_content_type_not_required(device: ServerFactory) -> None:
    async def handler(_: web.Request) -> web.Response:
        return web.Response(body=load_fixture("saltbuddy.json"), content_type="text/plain")

    server = await device(handler)
    async with aiohttp.ClientSession() as session:
        assert (await client_for(server, session).get_status()).salt_level == 64


async def test_request_headers_and_fresh_connection(device: ServerFactory) -> None:
    seen: list[web.Request] = []
    peers: list[tuple[str, int]] = []

    async def handler(request: web.Request) -> web.Response:
        seen.append(request)
        assert request.transport is not None
        peers.append(request.transport.get_extra_info("peername"))
        return web.Response(body=load_fixture("saltbuddy.json"))

    server = await device(handler)
    async with aiohttp.ClientSession() as session:
        client = client_for(server, session)
        await client.get_status()
        await client.get_status()
    assert [r.method for r in seen] == ["GET", "GET"]
    assert seen[0].headers["Connection"].lower() == "close"
    assert seen[0].headers["Accept"] == "application/json"
    # Each poll must use its own TCP connection so it never holds one of the device's sockets.
    assert peers[0] != peers[1]


# --- HTTP and body errors -------------------------------------------------------------------


@pytest.mark.parametrize("status", [404, 405, 500, 503])
async def test_http_error(device: ServerFactory, status: int) -> None:
    server = await device(body(b"", status=status))
    async with aiohttp.ClientSession() as session:
        with pytest.raises(RemonResponseError, match=str(status)):
            await client_for(server, session).get_status()


async def test_redirect_not_followed(device: ServerFactory) -> None:
    async def handler(_: web.Request) -> web.Response:
        raise web.HTTPFound("http://example.invalid/")

    server = await device(handler)
    async with aiohttp.ClientSession() as session:
        with pytest.raises(RemonResponseError, match="302"):
            await client_for(server, session).get_status()


async def test_wrong_path_is_404(aiohttp_server: Callable[..., Awaitable[TestServer]]) -> None:
    # Something else entirely answers on port 80 (a printer, a router page).
    server = await aiohttp_server(web.Application())
    async with aiohttp.ClientSession() as session:
        with pytest.raises(RemonResponseError, match="404"):
            await client_for(server, session).get_status()


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"<html>Not here</html>",
        b'{"id": "SaltBuddy-a1b2c3d4e5f6", ',
        b"\xff\xfe\x00{",
        b"NaN-ish",
        b"[" * 100_000,
        b"[" * 4000,
    ],
    ids=["empty", "html", "truncated", "not-utf8", "garbage", "huge", "deeply-nested"],
)
async def test_malformed_body(device: ServerFactory, raw: bytes) -> None:
    server = await device(body(raw))
    async with aiohttp.ClientSession() as session:
        with pytest.raises(RemonResponseError):
            await client_for(server, session).get_status()


async def test_body_at_size_limit_is_read(device: ServerFactory) -> None:
    padding = 4096 - len(load_fixture("saltbuddy.json"))
    raw = load_fixture("saltbuddy.json") + b" " * padding
    assert len(raw) == 4096
    server = await device(body(raw))
    async with aiohttp.ClientSession() as session:
        assert (await client_for(server, session).get_status()).salt_level == 64


async def test_incomplete_json(device: ServerFactory) -> None:
    server = await device(body(b'{"id":"SaltBuddy-a1b2c3d4e5f6","type":"SaltBuddy"}'))
    async with aiohttp.ClientSession() as session:
        with pytest.raises(RemonResponseError, match="fw"):
            await client_for(server, session).get_status()


async def test_unsupported_api(device: ServerFactory) -> None:
    server = await device(body(b'{"api":2}'))
    async with aiohttp.ClientSession() as session:
        with pytest.raises(RemonUnsupportedApiError):
            await client_for(server, session).get_status()


# --- connection errors ----------------------------------------------------------------------


async def test_timeout(device: ServerFactory) -> None:
    async def handler(_: web.Request) -> web.Response:
        await asyncio.sleep(5)
        return web.Response(body=load_fixture("saltbuddy.json"))  # pragma: no cover

    server = await device(handler)
    async with aiohttp.ClientSession() as session:
        with pytest.raises(RemonConnectionError, match="Timeout"):
            await client_for(server, session, request_timeout=0.1).get_status()


async def test_timeout_while_reading_body(device: ServerFactory) -> None:
    async def handler(request: web.Request) -> web.StreamResponse:
        response = web.StreamResponse()
        response.content_length = 200
        await response.prepare(request)
        await response.write(b'{"id":')
        await asyncio.sleep(5)
        return response  # pragma: no cover

    server = await device(handler)
    async with aiohttp.ClientSession() as session:
        with pytest.raises(RemonConnectionError, match="Timeout"):
            await client_for(server, session, request_timeout=0.2).get_status()


async def test_connection_refused() -> None:
    async with aiohttp.ClientSession() as session:
        client = RemonClient("127.0.0.1", session, port=free_port())
        with pytest.raises(RemonConnectionError):
            await client.get_status()


async def test_dns_failure() -> None:
    async with aiohttp.ClientSession() as session:
        client = RemonClient("does-not-exist.invalid", session, request_timeout=5)
        with pytest.raises(RemonConnectionError):
            await client.get_status()


async def test_connection_dropped_mid_response(device: ServerFactory) -> None:
    # The firmware restarts every 24 h; a poll can hit it halfway through a response.
    async def handler(request: web.Request) -> web.StreamResponse:
        response = web.StreamResponse()
        response.content_length = 200
        await response.prepare(request)
        await response.write(b'{"id":')
        assert request.transport is not None
        request.transport.close()
        return response

    server = await device(handler)
    async with aiohttp.ClientSession() as session:
        with pytest.raises(RemonConnectionError):
            await client_for(server, session).get_status()


async def test_connection_dropped_before_response(device: ServerFactory) -> None:
    async def handler(request: web.Request) -> web.Response:
        assert request.transport is not None
        request.transport.close()
        return web.Response()

    server = await device(handler)
    async with aiohttp.ClientSession() as session:
        with pytest.raises(RemonConnectionError):
            await client_for(server, session).get_status()


# --- construction and session ownership -----------------------------------------------------


@pytest.mark.parametrize("host", ["", "bad host", "a/b", "1.2.3.4:80"])
def test_invalid_host(host: str) -> None:
    with pytest.raises(ValueError, match=r"(?i)host"):
        RemonClient(host)


def test_properties() -> None:
    client = RemonClient("192.168.1.42", port=8080)
    assert client.host == "192.168.1.42"
    assert client.port == 8080


async def test_ipv6(aiohttp_server: Callable[..., Awaitable[TestServer]]) -> None:
    if not socket.has_ipv6:  # pragma: no cover
        pytest.skip("No IPv6")
    app = web.Application()
    app.router.add_get(STATUS_PATH, body(load_fixture("saltbuddy.json")))
    try:
        server = await aiohttp_server(app, host="::1")
    except OSError:  # pragma: no cover
        pytest.skip("IPv6 loopback not available")
    async with aiohttp.ClientSession() as session:
        client = RemonClient("::1", session, port=server.port)  # type: ignore[arg-type]
        assert (await client.get_status()).salt_level == 64


async def test_owns_session_when_none_given(device: ServerFactory) -> None:
    server = await device(body(load_fixture("saltbuddy.json")))
    assert server.port is not None
    async with RemonClient(server.host, port=server.port) as client:
        await client.get_status()
        session = client._session
        assert session is not None
    assert session.closed
    assert client._session is None
    # Usable again afterwards: a new session is created on demand.
    await client.get_status()
    await client.close()


async def test_does_not_close_shared_session(device: ServerFactory) -> None:
    server = await device(body(load_fixture("saltbuddy.json")))
    async with aiohttp.ClientSession() as session:
        async with client_for(server, session) as client:
            await client.get_status()
        assert not session.closed


async def test_close_without_request() -> None:
    client = RemonClient("192.168.1.42")
    await client.close()
