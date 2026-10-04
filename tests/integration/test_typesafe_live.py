"""REAL TypeSafe/Jev integration tests — hit the live API, no mocks.

Run: pytest -m typesafe
Requires TYPESAFE_API_KEY in the environment.
"""
from __future__ import annotations

import os
import time

import pytest

from jevlab.jev import (
    ChoiceAnswer,
    NoulAnswer,
    ScoreAnswer,
    TypeSafeClient,
    choice,
    noul,
    score,
)
from jevlab.passports.schema import Passport, SemanticValue
from jevlab.ranking.selector import EffectSelector

pytestmark = pytest.mark.typesafe

KEY_PRESENT = bool(os.environ.get("TYPESAFE_API_KEY"))


@pytest.fixture()
def client():
    if not KEY_PRESENT:
        pytest.skip("TYPESAFE_API_KEY not set")
    with TypeSafeClient() as c:
        yield c


def test_live_jev_answers_all_types(client):
    res = client.system_one(
        "A bright ring expands rapidly outward from a center point and "
        "fades in 400ms.",
        {
            "is_shockwave": noul("Is this a good candidate for a fast air "
                                 "shockwave impact?"),
            "role": choice("Best visual role?", {
                "shockwave": "expanding pressure wave / impact burst",
                "fire": "flame or burning",
                "smoke": "lingering smoke",
                "beam": "continuous directional ray",
            }),
            "intensity": score("Visual intensity?",
                               ["subtle", "moderate", "strong", "overwhelming"]),
        })
    assert res.model
    assert isinstance(res.answers["is_shockwave"], NoulAnswer)
    assert 0.0 <= res.answers["is_shockwave"].noul <= 1.0
    ca = res.answers["role"]
    assert isinstance(ca, ChoiceAnswer) and ca.choice == "shockwave"
    assert abs(sum(ca.probabilities.values()) - 1.0) < 0.05
    sa = res.answers["intensity"]
    assert isinstance(sa, ScoreAnswer) and sa.score >= 0
    assert res.usage.input_tokens > 0
    assert res.latency_s > 0


def _mk_passport(pid: str, kind: str, **kw) -> Passport:
    p = Passport(id=pid, source=kw.pop("source", "minecraft"),
                 namespace=pid.split(":")[0], kind=kind,
                 ready_to_use=True, primitive=True, **kw)
    return p


def test_live_find_effects_shockwave(client):
    """Mini-catalog end-to-end: real Noul stage + real Choice rerank."""
    ring = _mk_passport(
        "minecraft:sonic_boom", "particle",
        factual={"behavior": "expanding ring burst", "oneshot": True},
        visual={"shape": SemanticValue(["ring"], 0.95),
                "motion": SemanticValue(["radial expansion"], 0.95)})
    ring.possible_roles = SemanticValue(["shockwave", "impact"], 0.9)
    fire = _mk_passport(
        "minecraft:flame", "particle",
        factual={"behavior": "rising flame", "oneshot": False},
        visual={"shape": SemanticValue(["flicker"], 0.9),
                "motion": SemanticValue(["upward drift"], 0.85)})
    fire.possible_roles = SemanticValue(["fire", "torch"], 0.9)
    dust = _mk_passport(
        "minecraft:dust", "parameterized_particle", parameterized=True,
        parameter_schema={"color": "rgb", "scale": "float"},
        capabilities=["arbitrary_color", "variable_scale"],
        visual={"shape": SemanticValue(["motes"], 0.8)})
    smoke = _mk_passport(
        "minecraft:large_smoke", "particle",
        factual={"behavior": "expanding soft smoke puff", "oneshot": True},
        visual={"shape": SemanticValue(["cloud"], 0.9),
                "motion": SemanticValue(["slow expansion"], 0.85)})
    heart = _mk_passport(
        "minecraft:heart", "particle",
        visual={"shape": SemanticValue(["heart icon"], 0.99)})

    selector = EffectSelector(client, batch_size=4, stage2_pool=4, top_k=3)
    res = selector.find_effects(
        "need a very short powerful air impact from clapping hands; expands "
        "radially outward fast; no fire; no lingering smoke",
        [ring, fire, dust, smoke, heart])

    assert res.stage1_evaluated == 5 and res.stage1_batches == 2
    assert res.stage2_pool == 4
    assert len(res.candidates) == 3
    top = res.candidates[0]
    assert top.id == "minecraft:sonic_boom"
    assert top.noul_relevance is not None and top.noul_relevance > 0.5
    assert top.choice_probability is not None and top.choice_probability > 0.5
    assert res.choice_distribution
    ids = [c.id for c in res.candidates]
    # 'flame' contradicts the explicit "no fire" constraint. On a tiny
    # candidate list the fixed-size pool can still carry it through noul,
    # but stage-2 must assign it ~0 probability.
    flame = next((c for c in res.candidates if c.id == "minecraft:flame"), None)
    assert flame is None or flame.choice_probability == 0.0
    # 'heart' is irrelevant: it may survive into the pool on a tiny noul but
    # must be rejected in the final distribution
    heart = next((c for c in res.candidates if c.id == "minecraft:heart"), None)
    assert heart is None or heart.choice_probability == 0.0
    assert res.usage.input_tokens > 0 and res.latency_s > 0
