"""Exceptions raised by the Remon client.

Every error the library raises derives from :class:`RemonError`, so a caller that only wants to
know "did this poll work" can catch that one class.
"""

from __future__ import annotations


class RemonError(Exception):
    """Base class for all Remon client errors."""


class RemonConnectionError(RemonError):
    """The device could not be reached: timeout, connection refused, DNS failure, reset."""


class RemonResponseError(RemonError):
    """The device answered, but not with a valid status.

    Raised for a non-200 status code and for a body that is not JSON, is not a JSON object, or
    misses or mistypes a field of the status contract.
    """


class RemonUnsupportedApiError(RemonResponseError):
    """The firmware reports an ``api`` contract version newer than this library supports.

    The ``api`` number is only bumped on breaking changes, so the payload cannot be trusted.
    The fix is to update the Remon integration through HACS.
    """

    def __init__(self, api: int, supported: int) -> None:
        """Store the reported and supported contract versions."""
        super().__init__(
            f"Device speaks API version {api}, this library supports up to {supported}"
        )
        self.api = api
        self.supported = supported


class RemonDiscoveryError(RemonError):
    """An mDNS announcement does not carry a usable Remon identity (no valid ``id`` TXT record)."""
