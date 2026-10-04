"""Question builders and answer models for the TypeSafe systemone API.

Contract (verified against the live API, 2026-10-04, model jev-1.13.0):

Request:
    {"model": "...", "state": <any JSON>, "questions": {"name": question}}
    question := {"type": "noul",   "instructions": str, ["criteria": {...}]}
              | {"type": "choice", "instructions": str, "criteria": {label: description}}
              | {"type": "score",  "instructions": str, "criteria": [ordered rubric ...]}

Response:
    {"model": "<answered model>", "answers": {<name>: answer},
     "usage": {"input_tokens": int, "output_tokens": int}}

    noul   answer: {"type": "noul", "noul": float 0..1}
    choice answer: {"type": "choice", "choice": label, "confidence": float,
                    "probabilities": {label: float}}
    score  answer: {"type": "score", "score": float (weighted mean),
                    "confidence": float,
                    "legend": {"0": label0, ...},
                    "probabilities": {"0": p0, ...}}
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def noul(instructions: str, criteria: dict[str, str] | None = None) -> dict[str, Any]:
    """Independent yes/no judgment → probability of true in [0, 1]."""
    q: dict[str, Any] = {"type": "noul", "instructions": instructions}
    if criteria is not None:
        q["criteria"] = criteria
    return q


def choice(instructions: str, criteria: dict[str, str]) -> dict[str, Any]:
    """Pick one label from criteria → label + full probability distribution."""
    if not criteria:
        raise ValueError("choice requires a non-empty criteria map")
    return {"type": "choice", "instructions": instructions, "criteria": dict(criteria)}


def score(instructions: str, criteria: list[str]) -> dict[str, Any]:
    """Ordered rubric → weighted score + per-level probabilities."""
    if not criteria:
        raise ValueError("score requires a non-empty ordered criteria list")
    return {"type": "score", "instructions": instructions, "criteria": list(criteria)}


@dataclass(frozen=True)
class NoulAnswer:
    noul: float


@dataclass(frozen=True)
class ChoiceAnswer:
    choice: str
    confidence: float
    probabilities: dict[str, float]


@dataclass(frozen=True)
class ScoreAnswer:
    score: float
    confidence: float
    legend: dict[str, str]
    probabilities: dict[str, float]


Answer = NoulAnswer | ChoiceAnswer | ScoreAnswer


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(self.input_tokens + other.input_tokens,
                     self.output_tokens + other.output_tokens)


@dataclass(frozen=True)
class SystemOneResult:
    model: str
    answers: dict[str, Answer]
    usage: Usage
    latency_s: float
    raw: dict[str, Any] = field(repr=False, default_factory=dict)


def parse_answer(name: str, payload: dict[str, Any]) -> Answer:
    """Parse one entry of the `answers` map. Raises JevResponseError on contract mismatch."""
    from .errors import JevResponseError

    qtype = payload.get("type")
    try:
        if qtype == "noul":
            return NoulAnswer(noul=float(payload["noul"]))
        if qtype == "choice":
            probs = payload.get("probabilities")
            if not isinstance(probs, dict):
                raise KeyError("probabilities")
            return ChoiceAnswer(
                choice=str(payload["choice"]),
                confidence=float(payload.get("confidence", 0.0)),
                probabilities={str(k): float(v) for k, v in probs.items()},
            )
        if qtype == "score":
            probs = payload.get("probabilities", {})
            return ScoreAnswer(
                score=float(payload["score"]),
                confidence=float(payload.get("confidence", 0.0)),
                legend={str(k): str(v) for k, v in (payload.get("legend") or {}).items()},
                probabilities={str(k): float(v) for k, v in probs.items()},
            )
    except (KeyError, TypeError, ValueError) as exc:
        raise JevResponseError(
            f"answer {name!r} failed contract ({qtype!r}): {exc}") from exc
    raise JevResponseError(f"answer {name!r} has unknown type {qtype!r}")
