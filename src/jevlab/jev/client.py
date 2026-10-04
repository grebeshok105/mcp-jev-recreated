"""TypeSafe Jev client — POST /v1/systemone.

Sync httpx client with bounded exponential-backoff retries, 429/Retry-After
support, per-request latency and token-usage accounting.

Env:
    TYPESAFE_API_KEY  — Bearer credential (required unless api_key passed)
    TYPESAFE_BASE_URL — override base URL (default https://api.typesafe.ai)
"""
from __future__ import annotations

import os
import random
import time
from typing import Any

import httpx

from .errors import (
    JevAPIError,
    JevAuthError,
    JevNetworkError,
    JevRateLimitError,
    JevResponseError,
)
from .questions import SystemOneResult, Usage, parse_answer

DEFAULT_BASE_URL = "https://api.typesafe.ai"
DEFAULT_MODEL = "jev-latest"

# Retryable: transport failures, 429, and 5xx. Everything else fails fast.
_RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})


class TypeSafeClient:
    """Thin, honest wrapper over the systemone endpoint.

    One call = one synchronous forward pass: every question in the request is
    answered independently in a single response.
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str | None = None,
        model: str = DEFAULT_MODEL,
        timeout_s: float = 60.0,
        max_retries: int = 4,
        backoff_base_s: float = 0.5,
        backoff_max_s: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ):
        self.api_key = api_key if api_key is not None else os.environ.get("TYPESAFE_API_KEY")
        if not self.api_key:
            raise JevAuthError(
                0, "missing API key — pass api_key or set TYPESAFE_API_KEY")
        self.base_url = (base_url or os.environ.get("TYPESAFE_BASE_URL")
                         or DEFAULT_BASE_URL).rstrip("/")
        self.model = model
        self.timeout_s = timeout_s
        if max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        self.max_retries = max_retries
        self.backoff_base_s = backoff_base_s
        self.backoff_max_s = backoff_max_s
        self._client = httpx.Client(
            transport=transport,
            timeout=httpx.Timeout(timeout_s),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "jevlab/0.1",
            },
        )
        # cumulative diagnostics across the client's life
        self.usage_totals = Usage()
        self.request_count = 0
        self.retry_count = 0

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "TypeSafeClient":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # ------------------------------------------------------------------ API

    def system_one(
        self,
        state: Any,
        questions: dict[str, dict[str, Any]],
        *,
        model: str | None = None,
        deadline_s: float | None = None,
    ) -> SystemOneResult:
        """Evaluate `questions` against `state` in one parallel forward pass.

        `deadline_s` optionally bounds the whole call including retries.
        Raises JevAuthError/JevRateLimitError/JevNetworkError/JevAPIError/
        JevResponseError.
        """
        if not questions:
            raise ValueError("questions must be non-empty")
        body = {"model": model or self.model, "state": state, "questions": questions}
        raw, latency = self._post_with_retry("/v1/systemone", body, deadline_s)
        result = self._parse_result(raw, latency)
        self.usage_totals = self.usage_totals + result.usage
        return result

    # ------------------------------------------------------------- internals

    def _post_with_retry(
        self, path: str, body: dict[str, Any], deadline_s: float | None
    ) -> tuple[dict[str, Any], float]:
        started = time.monotonic()
        attempts = 0
        last_exc: Exception | None = None
        while attempts <= self.max_retries:
            # the first attempt always runs — the deadline bounds retries only
            if attempts > 0 and deadline_s is not None \
                    and time.monotonic() - started > deadline_s:
                break
            try:
                req_started = time.monotonic()
                resp = self._client.post(self.base_url + path, json=body)
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                last_exc = JevNetworkError(f"transport failure: {exc}")
                delay = self._retry_delay(attempts, None)
                if not self._sleep_retry(delay, attempts, started, deadline_s):
                    break
                attempts += 1
                continue

            if resp.status_code == 200:
                self.request_count += 1
                return self._decode(resp), time.monotonic() - req_started

            last_exc = self._http_error(resp)
            if resp.status_code not in _RETRYABLE_STATUSES:
                break  # deterministic failure — do not retry
            delay = self._retry_delay(attempts, self._retry_after(resp))
            if not self._sleep_retry(delay, attempts, started, deadline_s):
                break
            attempts += 1

        self.retry_count += attempts
        assert last_exc is not None
        raise last_exc

    def _sleep_retry(
        self, delay: float, attempts: int, started: float, deadline_s: float | None
    ) -> bool:
        if attempts >= self.max_retries:
            return False
        if deadline_s is not None:
            remaining = deadline_s - (time.monotonic() - started)
            if remaining <= 0:
                return False
            delay = min(delay, remaining)
        time.sleep(delay)
        return True

    def _retry_delay(self, attempts: int, retry_after: float | None) -> float:
        if retry_after is not None:
            return min(retry_after, self.backoff_max_s)
        delay = self.backoff_base_s * (2 ** attempts)
        return min(delay + random.uniform(0, delay * 0.25), self.backoff_max_s)

    @staticmethod
    def _retry_after(resp: httpx.Response) -> float | None:
        value = resp.headers.get("Retry-After")
        if value is None:
            return None
        try:
            return max(0.0, float(value))
        except ValueError:
            return None

    @staticmethod
    def _decode(resp: httpx.Response) -> dict[str, Any]:
        try:
            payload = resp.json()
        except ValueError as exc:
            raise JevResponseError(
                f"HTTP 200 but non-JSON body ({len(resp.content)} bytes)") from exc
        if not isinstance(payload, dict):
            raise JevResponseError("HTTP 200 but payload is not a JSON object")
        return payload

    @staticmethod
    def _http_error(resp: httpx.Response) -> JevAPIError:
        request_id = resp.headers.get("x-request-id") or resp.headers.get("request-id")
        body_text = resp.text[:2000] if resp.text else ""
        message = body_text or resp.reason_phrase or "unknown"
        try:
            err = resp.json()
            if isinstance(err, dict):
                message = str(err.get("error") or err.get("message") or message)
        except ValueError:
            pass
        if resp.status_code in (401, 403):
            return JevAuthError(resp.status_code, message,
                                request_id=request_id, body=body_text)
        if resp.status_code == 429:
            retry_after = None
            try:
                retry_after = float(resp.headers["Retry-After"])
            except (KeyError, ValueError):
                pass
            return JevRateLimitError(message, request_id=request_id,
                                     retry_after=retry_after, body=body_text)
        return JevAPIError(resp.status_code, message,
                           request_id=request_id, body=body_text)

    @staticmethod
    def _parse_result(raw: dict[str, Any], latency_s: float) -> SystemOneResult:
        answers_raw = raw.get("answers")
        if not isinstance(answers_raw, dict):
            raise JevResponseError("response lacks an 'answers' object")
        answers = {name: parse_answer(name, a) for name, a in answers_raw.items()}
        usage_raw = raw.get("usage") or {}
        usage = Usage(
            input_tokens=int(usage_raw.get("input_tokens", 0)),
            output_tokens=int(usage_raw.get("output_tokens", 0)),
        )
        return SystemOneResult(
            model=str(raw.get("model", "")),
            answers=answers,
            usage=usage,
            latency_s=latency_s,
            raw=raw,
        )
