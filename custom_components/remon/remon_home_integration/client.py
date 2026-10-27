"""Async client for the Remon device's local HTTP API."""

from __future__ import annotations

import asyncio
import json
from types import TracebackType
from typing import Self

import aiohttp
from yarl import URL

from .exceptions import RemonConnectionError, RemonResponseError
from .models import RemonStatus

DEFAULT_PORT = 80
DEFAULT_TIMEOUT = 10.0
STATUS_PATH = "/api/status"

# The status body is about 150 bytes. Anything far bigger is not a Remon device; do not buffer it.
_MAX_BODY_BYTES = 4096


class RemonClient:
    """Read the status of one Remon device over HTTP on the LAN.

    The API is read-only and unauthenticated, so the client has no credentials and no write
    methods. Pass Home Assistant's shared ``aiohttp.ClientSession``; without one the client
    creates its own and closes it in :meth:`close` (or when used as an async context manager).
    """

    def __init__(
        self,
        host: str,
        session: aiohttp.ClientSession | None = None,
        *,
        port: int = DEFAULT_PORT,
        request_timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        """Prepare a client for ``host`` (IPv4, IPv6 or hostname, without scheme or port).

        Raises:
            ValueError: ``host`` or ``port`` cannot form a valid URL.

        """
        if not host:
            raise ValueError("host must not be empty")
        self._host = host
        self._port = port
        self._url = URL.build(scheme="http", host=host, port=port, path=STATUS_PATH)
        self._session = session
        self._close_session = False
        self._timeout = request_timeout

    @property
    def host(self) -> str:
        """Host this client talks to."""
        return self._host

    @property
    def port(self) -> int:
        """TCP port this client talks to."""
        return self._port

    async def get_status(self) -> RemonStatus:
        """Fetch and validate ``GET /api/status``.

        Raises:
            RemonConnectionError: The device could not be reached in time.
            RemonUnsupportedApiError: The firmware speaks a newer contract version.
            RemonResponseError: The device answered with something other than a valid status.

        """
        data = await self._get_json()
        return RemonStatus.from_dict(data)

    async def _get_json(self) -> object:
        if self._session is None:
            self._session = aiohttp.ClientSession()
            self._close_session = True

        try:
            async with (
                asyncio.timeout(self._timeout),
                self._session.get(
                    self._url,
                    # The firmware serves at most two sockets (Home Assistant and Homey). A
                    # kept-alive socket would hold one of them between polls, and one the device
                    # recycled would fail the next poll, so use a fresh connection every time.
                    headers={"Accept": "application/json", "Connection": "close"},
                    allow_redirects=False,
                ) as response,
            ):
                if response.status != 200:
                    raise RemonResponseError(f"{self._url} answered HTTP {response.status}")
                body = await _read_limited(response, _MAX_BODY_BYTES + 1)
        except TimeoutError as err:
            raise RemonConnectionError(
                f"Timeout after {self._timeout:g} s talking to {self._url}"
            ) from err
        except aiohttp.ClientError as err:
            raise RemonConnectionError(
                f"Error talking to {self._url}: {type(err).__name__}: {err}"
            ) from err

        if len(body) > _MAX_BODY_BYTES:
            raise RemonResponseError(f"Response from {self._url} exceeds {_MAX_BODY_BYTES} bytes")
        try:
            return json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError, RecursionError) as err:
            raise RemonResponseError(f"Response from {self._url} is not valid JSON") from err

    async def close(self) -> None:
        """Close the HTTP session if this client created it."""
        if self._session is not None and self._close_session:
            await self._session.close()
            self._session = None
            self._close_session = False

    async def __aenter__(self) -> Self:
        """Enter the async context."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Close the session the client created, if any."""
        await self.close()


async def _read_limited(response: aiohttp.ClientResponse, limit: int) -> bytes:
    """Read the body until EOF or ``limit`` bytes, whichever comes first.

    ``StreamReader.read(n)`` returns whatever is buffered, so a body that arrives in several TCP
    segments needs a loop. A connection closed before the announced length raises
    ``aiohttp.ClientPayloadError``.
    """
    content = response.content
    body = bytearray()
    while len(body) < limit:
        chunk = await content.read(limit - len(body))
        if not chunk:
            break
        body += chunk
    return bytes(body)
