"""findEffects — two-stage Jev ranking over the VFX catalog.

Stage 1 (Noul): independent relevance. Each candidate is scored against the
query by its own noul question inside batched systemone requests (one forward
pass answers every question in the request). Noul scores are independent per
candidate, hence comparable across batches — unlike Choice probabilities,
which are only meaningful *within* one question's distribution.

Stage 2 (Choice): the top-N survivors of stage 1 go into a single Choice whose
criteria keys are the candidate ids. The returned probability distribution
ranks the finalists; we keep the full distribution and publish top-K.

Stage order and sizes are configured, not hard-coded: they were tuned on the
real catalog and live API during evaluation.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from ..jev.client import TypeSafeClient
from ..jev.questions import ChoiceAnswer, NoulAnswer, Usage, choice, noul
from ..passports.schema import Passport

RANKER_VERSION = 1

NOUL_INSTRUCTIONS = (
    "You are given a user request for a Minecraft visual effect and a catalog "
    "of real, existing visual resources (vanilla particles, parameterized "
    "particles, world events, Photon FX/emitters/trails/beams, modded "
    "particles, composite effects). Judge ONLY this candidate: is it a good "
    "basis to implement the requested effect, usable as-is or through its "
    "documented parameters? Judge by the resource's factual and measured data "
    "and visual semantics — not by its name. Answer true when the resource "
    "credibly produces the requested look; answer false when it only weakly "
    "matches, contradicts explicit constraints of the request, or would "
    "require being a different effect."
)

CHOICE_INSTRUCTIONS = (
    "Pick the single resource that best satisfies the user's visual-effect "
    "request, judging by what each resource actually looks like (visual "
    "semantics, measured behavior, parameters) — never by its name alone. "
    "Respect explicit exclusions in the request (e.g. 'no fire', 'no "
    "lingering smoke') as hard constraints."
)


@dataclass
class RankedCandidate:
    rank: int
    id: str
    source: str
    kind: str
    noul_relevance: float | None
    choice_probability: float | None
    ready_to_use: bool
    summary: str


@dataclass
class FindResult:
    query: str
    candidates: list[RankedCandidate]
    stage1_evaluated: int
    stage1_batches: int
    stage2_pool: int
    choice_distribution: dict[str, float] = field(default_factory=dict)
    usage: Usage = field(default_factory=Usage)
    latency_s: float = 0.0
    diagnostics: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "candidates": [vars(c) for c in self.candidates],
            "stats": {
                "stage1_evaluated": self.stage1_evaluated,
                "stage1_batches": self.stage1_batches,
                "stage2_pool": self.stage2_pool,
                "usage": {"input_tokens": self.usage.input_tokens,
                          "output_tokens": self.usage.output_tokens},
                "latency_s": round(self.latency_s, 3),
            },
            "choice_distribution": self.choice_distribution,
            "diagnostics": self.diagnostics,
        }


def _chunks(seq: Sequence[Any], size: int) -> Iterable[Sequence[Any]]:
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


class EffectSelector:
    def __init__(
        self,
        client: TypeSafeClient,
        *,
        batch_size: int = 12,
        stage2_pool: int = 12,
        top_k: int = 10,
        deadline_s: float | None = None,
    ):
        if batch_size < 1:
            raise ValueError("batch_size must be >= 1")
        if stage2_pool < 1 or top_k < 1:
            raise ValueError("stage2_pool/top_k must be >= 1")
        self.client = client
        self.batch_size = batch_size
        self.stage2_pool = stage2_pool
        self.top_k = top_k
        self.deadline_s = deadline_s

    # ------------------------------------------------------------ stage 1

    def _stage1(self, query: str,
                passports: Sequence[Passport],
                result: FindResult) -> dict[str, float]:
        relevance: dict[str, float] = {}
        for batch in _chunks(passports, self.batch_size):
            result.stage1_batches += 1
            state = {
                "user_request": query,
                "candidates": {
                    p.id: p.jev_brief() for p in batch
                },
            }
            questions = {
                f"c{i}": noul(
                    f"{NOUL_INSTRUCTIONS}\n\nCandidate under judgment: \"{p.id}\"")
                for i, p in enumerate(batch)
            }
            resp = self.client.system_one(state, questions,
                                          deadline_s=self.deadline_s)
            result.usage = result.usage + resp.usage
            for i, p in enumerate(batch):
                ans = resp.answers.get(f"c{i}")
                if isinstance(ans, NoulAnswer):
                    relevance[p.id] = ans.noul
                else:
                    relevance[p.id] = 0.0
                    result.diagnostics.append(
                        f"stage1: missing/invalid noul for {p.id} — scored 0")
        result.stage1_evaluated = len(relevance)
        return relevance

    # ------------------------------------------------------------ stage 2

    def _stage2(self, query: str,
                finalists: Sequence[Passport],
                result: FindResult) -> dict[str, float]:
        if not finalists:
            return {}
        state = {
            "user_request": query,
            "candidates": {p.id: p.jev_brief() for p in finalists},
        }
        criteria = {p.id: p.one_line() for p in finalists}
        questions = {"pick": choice(CHOICE_INSTRUCTIONS, criteria)}
        resp = self.client.system_one(state, questions,
                                      deadline_s=self.deadline_s)
        result.usage = result.usage + resp.usage
        ans = resp.answers.get("pick")
        if not isinstance(ans, ChoiceAnswer):
            result.diagnostics.append("stage2: choice answer missing — "
                                      "falling back to noul order")
            return {}
        result.choice_distribution = dict(ans.probabilities)
        return ans.probabilities

    # ------------------------------------------------------------- public

    def find_effects(
        self,
        query: str,
        passports: Sequence[Passport],
        *,
        top_k: int | None = None,
        stage2_pool: int | None = None,
    ) -> FindResult:
        started = time.monotonic()
        result = FindResult(query=query, candidates=[], stage1_evaluated=0,
                            stage1_batches=0, stage2_pool=0)
        pool = self.stage2_pool if stage2_pool is None else stage2_pool
        k = self.top_k if top_k is None else top_k

        relevance = self._stage1(query, passports, result)
        by_id = {p.id: p for p in passports}
        ordered = sorted(relevance.items(), key=lambda kv: (-kv[1], kv[0]))
        finalists = [by_id[i] for i, _ in ordered[:pool]]
        result.stage2_pool = len(finalists)

        probs = self._stage2(query, finalists, result)
        if probs:
            final_order = sorted(finalists,
                                 key=lambda p: (-probs.get(p.id, 0.0), p.id))
        else:
            final_order = finalists  # noul order fallback

        for rank, p in enumerate(final_order[:k], start=1):
            result.candidates.append(RankedCandidate(
                rank=rank, id=p.id, source=p.source, kind=p.kind,
                noul_relevance=relevance.get(p.id),
                choice_probability=probs.get(p.id),
                ready_to_use=p.ready_to_use,
                summary=p.one_line(),
            ))
        result.latency_s = time.monotonic() - started
        return result
