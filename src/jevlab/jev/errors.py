"""Typed errors for the TypeSafe/Jev client."""
from __future__ import annotations


class JevError(Exception):
    """Base error for all Jev client failures."""


class JevAPIError(JevError):
    """HTTP error returned by the TypeSafe API."""

    def __init__(self, status: int, message: str, *, request_id: str | None = None,
                 body: str | None = None):
        super().__init__(f"TypeSafe API error {status}: {message}")
        self.status = status
        self.request_id = request_id
        self.body = body


class JevAuthError(JevAPIError):
    """401/403 — bad or missing credentials."""


class JevRateLimitError(JevAPIError):
    """429 after exhausting retries. Carries the last seen Retry-After."""

    def __init__(self, message: str, *, request_id: str | None = None,
                 retry_after: float | None = None, body: str | None = None):
        super().__init__(429, message, request_id=request_id, body=body)
        self.retry_after = retry_after


class JevNetworkError(JevError):
    """Transport-level failure (DNS, TCP, TLS, timeout) after exhausting retries."""


class JevResponseError(JevError):
    """HTTP 200 but the payload does not match the systemone contract."""
