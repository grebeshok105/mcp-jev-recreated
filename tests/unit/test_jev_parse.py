"""Unit tests: question builders, answer parsing, client error handling.

API-contract tests against the REAL TypeSafe service live in
tests/integration/test_typesafe_live.py (marked `typesafe`).
"""
from __future__ import annotations

import httpx
import pytest

from jevlab.jev import (
    JevAuthError,
    JevNetworkError,
    JevRateLimitError,
    JevResponseError,
    TypeSafeClient,
    choice,
    noul,
    score,
)
from jevlab.jev.questions import ChoiceAnswer, NoulAnswer, ScoreAnswer


# ---------------------------------------------------------------- builders

def test_noul_builder_minimal():
    assert noul("is it red?") == {"type": "noul", "instructions": "is it red?"}


def test_choice_builder_copies_criteria():
    crit = {"a": "option a", "b": "option b"}
    q = choice("pick", crit)
    assert q["type"] == "choice" and q["criteria"] == crit
    crit["c"] = "mutated"
    assert "c" not in q["criteria"]


def test_score_builder_ordered():
    q = score("rate", ["low", "high"])
    assert q == {"type": "score", "instructions": "rate",
                 "criteria": ["low", "high"]}


def test_choice_rejects_empty():
    with pytest.raises(ValueError):
        choice("pick", {})


# ------------------------------------------------------------------ parsing

def _ok_response(answers, model="jev-1.13.0"):
    return httpx.Response(200, json={
        "model": model,
        "answers": answers,
        "usage": {"input_tokens": 10, "output_tokens": 5},
    })


def _client(handler, **kw):
    transport = httpx.MockTransport(handler)
    return TypeSafeClient(api_key="test-key", transport=transport, **kw)


def test_system_one_parses_all_types():
    def handler(req: httpx.Request) -> httpx.Response:
        import json
        body = json.loads(req.content)
        assert body["model"] == "jev-latest"
        assert body["questions"]["n"]["type"] == "noul"
        return _ok_response({
            "n": {"type": "noul", "noul": 0.78},
            "c": {"type": "choice", "choice": "b", "confidence": 0.5,
                  "probabilities": {"a": 0.2, "b": 0.8}},
            "s": {"type": "score", "score": 1.7, "confidence": 0.6,
                  "legend": {"0": "low", "1": "mid", "2": "high"},
                  "probabilities": {"0": 0.1, "1": 0.3, "2": 0.6}},
        })
    with _client(handler) as client:
        res = client.system_one("state", {
            "n": noul("q"), "c": choice("q", {"a": "x", "b": "y"}),
            "s": score("q", ["low", "mid", "high"])})
    assert isinstance(res.answers["n"], NoulAnswer) and res.answers["n"].noul == 0.78
    ca = res.answers["c"]
    assert isinstance(ca, ChoiceAnswer) and ca.choice == "b" and ca.probabilities["b"] == 0.8
    sa = res.answers["s"]
    assert isinstance(sa, ScoreAnswer) and sa.score == 1.7 and sa.legend["2"] == "high"
    assert res.usage.input_tokens == 10 and res.usage.output_tokens == 5
    assert res.latency_s >= 0


def test_malformed_answer_raises_response_error():
    def handler(req):
        return _ok_response({"n": {"type": "noul", "noul": "NaNish"}})
    with _client(handler) as client:
        with pytest.raises(JevResponseError):
            client.system_one("s", {"n": noul("q")})


def test_unknown_answer_type_raises():
    def handler(req):
        return _ok_response({"x": {"type": "banana", "v": 1}})
    with _client(handler) as client:
        with pytest.raises(JevResponseError):
            client.system_one("s", {"x": noul("q")})


def test_missing_answers_object_raises():
    def handler(req):
        return httpx.Response(200, json={"model": "m"})
    with _client(handler) as client:
        with pytest.raises(JevResponseError):
            client.system_one("s", {"x": noul("q")})


# -------------------------------------------------------------------- errors

def test_auth_error_not_retried():
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(401, json={"error": "bad key"})
    with _client(handler, max_retries=3) as client:
        with pytest.raises(JevAuthError):
            client.system_one("s", {"x": noul("q")})
    assert len(calls) == 1  # no retries on auth


def test_429_retries_then_rate_limit_error():
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(429, json={"error": "slow down"},
                              headers={"Retry-After": "0"})
    with _client(handler, max_retries=2, backoff_base_s=0) as client:
        with pytest.raises(JevRateLimitError):
            client.system_one("s", {"x": noul("q")})
    assert len(calls) == 3  # initial + 2 retries


def test_429_recovers():
    calls = []

    def handler(req):
        calls.append(1)
        if len(calls) < 2:
            return httpx.Response(429, json={"error": "rl"},
                                  headers={"Retry-After": "0"})
        return _ok_response({"x": {"type": "noul", "noul": 0.5}})
    with _client(handler, max_retries=3, backoff_base_s=0) as client:
        res = client.system_one("s", {"x": noul("q")})
    assert res.answers["x"].noul == 0.5
    assert len(calls) == 2


def test_network_error_retries_then_raises():
    calls = []

    def handler(req):
        calls.append(1)
        raise httpx.ConnectError("boom")
    with _client(handler, max_retries=1, backoff_base_s=0) as client:
        with pytest.raises(JevNetworkError):
            client.system_one("s", {"x": noul("q")})
    assert len(calls) == 2


def test_500_retried_400_not():
    calls = []

    def handler(req):
        calls.append(req.url.path)
        if "first" in req.url.path:
            return httpx.Response(500, json={"error": "srv"})
        return httpx.Response(400, json={"error": "bad request"})
    # smoke: server error
    def h500(req):
        calls.append(1)
        return httpx.Response(500, json={"error": "srv"})
    with _client(h500, max_retries=2, backoff_base_s=0) as client:
        with pytest.raises(Exception) as ei:
            client.system_one("s", {"x": noul("q")})
    from jevlab.jev import JevAPIError
    assert isinstance(ei.value, JevAPIError) and ei.value.status == 500
    assert len(calls) == 3

    calls.clear()

    def h400(req):
        calls.append(1)
        return httpx.Response(400, json={"error": "bad request"})
    with _client(h400, max_retries=3, backoff_base_s=0) as client:
        with pytest.raises(JevAPIError) as ei:
            client.system_one("s", {"x": noul("q")})
    assert ei.value.status == 400 and len(calls) == 1


def test_missing_key_raises():
    import os
    saved = os.environ.pop("TYPESAFE_API_KEY", None)
    try:
        with pytest.raises(JevAuthError):
            TypeSafeClient(api_key=None)
    finally:
        if saved:
            os.environ["TYPESAFE_API_KEY"] = saved


def test_deadline_bounds_retries():
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(429, json={"error": "rl"},
                              headers={"Retry-After": "0"})
    with _client(handler, max_retries=99, backoff_base_s=0) as client:
        with pytest.raises(JevRateLimitError):
            client.system_one("s", {"x": noul("q")}, deadline_s=0.0)
    assert len(calls) == 1  # deadline exceeded before first retry


def test_empty_questions_rejected():
    with _client(lambda r: _ok_response({})) as client:
        with pytest.raises(ValueError):
            client.system_one("s", {})
