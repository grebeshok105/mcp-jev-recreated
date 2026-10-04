"""Pipeline tests: providers -> catalog -> measured -> visual -> selector.

Runs against the committed probe artifacts under data/ — no game, no API.
Selector tests use a stub client; the live TypeSafe path is covered by
tests/integration/test_typesafe_live.py.
"""
from __future__ import annotations

import json
import os

import pytest

from jevlab.catalog.builder import Catalog, CatalogBuilder
from jevlab.enrichment.measured import apply_measured, shot_resource_id
from jevlab.enrichment.visual import apply_visual, merge_passes, _tokens
from jevlab.find_effects import answerable, find
from jevlab.jev.questions import ChoiceAnswer, NoulAnswer, SystemOneResult, Usage
from jevlab.passports.schema import Passport
from jevlab.providers.base import ProviderContext
from jevlab.providers.particles import PARAM_SCHEMAS, ParticleTypesProvider
from jevlab.providers.photon import PhotonProvider
from jevlab.providers.quasar import QuasarProvider
from jevlab.providers.world_events import WorldEventsProvider
from jevlab.ranking.selector import EffectSelector

DATA = os.path.join(os.path.dirname(__file__), "..", "..", "data")
CTX = ProviderContext(data_dir=DATA, raw_dir=DATA)


@pytest.fixture(scope="module")
def catalog():
    return CatalogBuilder([
        ParticleTypesProvider(), WorldEventsProvider(),
        PhotonProvider(), QuasarProvider(),
    ]).build(CTX)


# ------------------------------------------------------------- providers

def test_particle_types_all_namespaces(catalog):
    p = catalog.get("minecraft:dust")
    assert p is not None and p.parameterized
    assert p.parameter_schema == PARAM_SCHEMAS["minecraft:dust"]
    assert catalog.get("superheroes:white_boom") is not None
    assert catalog.stats.by_source["particles"] == 142


def test_world_events_flagged_visual(catalog):
    visual = catalog.get("minecraft:world_event/PARTICLES_DESTROY_BLOCK")
    assert visual is not None and visual.factual["has_visual"]
    sound = catalog.get("minecraft:world_event/SOUND_DISPENSER_DISPENSE")
    assert sound is not None and not sound.factual["has_visual"]


def test_quasar_emitters_ready(catalog):
    e = catalog.get("superheroes:homelander_roar_wave")
    assert e is not None and e.kind == "quasar_emitter" and e.ready_to_use
    assert catalog.stats.by_kind["quasar_emitter"] == 15


def test_photon_textures_are_materials_not_answers(catalog):
    t = catalog.get("photon:texture/minecraft:textures/block/stone.png")
    assert t is not None and t.kind == "texture" and not t.ready_to_use


def test_no_id_collisions_across_kinds(catalog):
    ids = [p.id for p in catalog.resources.values()]
    assert len(ids) == len(set(ids))
    # quasar particle defs must not shadow particle types
    assert catalog.get("minecraft:ash") is not None
    assert catalog.get("minecraft:ash").kind == "particle"
    assert catalog.get("minecraft:particle_def/ash") is not None


def test_provider_isolation_missing_artifact(tmp_path):
    ctx = ProviderContext(data_dir=str(tmp_path), raw_dir=str(tmp_path))
    cat = CatalogBuilder([ParticleTypesProvider()]).build(ctx)
    assert cat.stats.failed_sources == ["particles"]
    assert cat.stats.total == 0


# ------------------------------------------------------------ measured

def test_shot_resource_id_mapping():
    assert shot_resource_id("minecraft_dust") == "minecraft:dust"
    assert shot_resource_id("superheroes_homelander_roar_wave") == \
        "superheroes:homelander_roar_wave"
    assert shot_resource_id("levelevent_2001") == \
        "minecraft:world_event/PARTICLES_DESTROY_BLOCK"


def test_measured_layer_merged(catalog):
    diags = apply_measured(
        catalog, os.path.join(DATA, "capture/measurements/capture_results.json"))
    assert diags == []
    m = catalog.get("minecraft:dust").measured
    assert m["spawned_max"] > 0 and m["peak_alive"] > 0
    assert "extent_blocks" in m and len(m["extent_blocks"]) == 3
    assert m["frames_captured"] > 0
    q = catalog.get("superheroes:homelander_roar_wave").measured
    assert q["capture_kind"] == "quasar_emitter" and q["peak_alive"] > 0


# --------------------------------------------------------------- visual

def _pass(shot, props, vis="clear", conf=0.9, roles=None):
    return {"observations": {shot: {
        "visibility": vis, "description": "desc",
        "properties": props, "possible_roles": roles or [],
        "confidence": conf}}}


def test_tokens_strip_timing_and_stopwords():
    assert _tokens("dense at t3, sparse by t8") == {"dense", "sparse"}
    assert _tokens("bright glow") == {"bright", "glow"}


def test_merge_no_disagreement_on_shared_terms():
    a = _pass("s1", {"shape": ["round puff blob"], "motion": ["expands out"]})
    b = _pass("s1", {"shape": ["puff of specks"], "motion": ["expands outward"]})
    m = merge_passes([a, b])["s1"]["visual"]
    assert not m["shape"].disagreement
    assert not m["motion"].disagreement
    assert sorted(m["shape"].values) == ["puff of specks", "round puff blob"]


def test_merge_flags_real_disagreement():
    a = _pass("s1", {"brightness": ["bright", "glowing"]})
    b = _pass("s1", {"brightness": ["matte", "dim"]})
    m = merge_passes([a, b])["s1"]["visual"]
    assert m["brightness"].disagreement
    assert m["brightness"].evidence == ["a", "b"]


def test_merge_visibility_conflict_flagged():
    a = _pass("s1", {}, vis="clear")
    b = _pass("s1", {}, vis="none")
    m = merge_passes([a, b])["s1"]["visual"]
    assert m["visibility"].disagreement


def test_apply_visual_real_files(catalog):
    diags = apply_visual(catalog, [os.path.join(DATA, "visual/pass_a.json"),
                                   os.path.join(DATA, "visual/pass_b.json")])
    assert diags == []
    v = catalog.get("minecraft:dust").visual
    assert "cyan" in " ".join(v["dominant_colors"].values)
    assert catalog.get("vfxlab:laser_beam").possible_roles is not None


# ----------------------------------------------------------- answerable

def test_answerable_excludes_materials(catalog):
    ids = {p.id for p in answerable(catalog)}
    assert "minecraft:dust" in ids
    assert "superheroes:homelander_roar_wave" in ids
    assert "photon:texture/minecraft:textures/block/stone.png" not in ids
    # sound-only events excluded
    assert not any(i.startswith("minecraft:world_event/SOUND_") for i in ids)


# ------------------------------------------------------------- selector

class _StubClient:
    """Returns deterministic answers: noul=1.0 for ids containing 'dust',
    choice concentrated on the alphabetically-first finalist."""

    def __init__(self):
        self.requests = 0

    def system_one(self, state, questions, *, deadline_s=None):
        self.requests += 1
        answers = {}
        for name, q in questions.items():
            if q["type"] == "noul":
                answers[name] = NoulAnswer(1.0 if "dust" in q["instructions"]
                                           else 0.05)
            elif q["type"] == "choice":
                first = sorted(q["criteria"])[0]
                probs = {k: 0.0 for k in q["criteria"]}
                probs[first] = 1.0
                answers[name] = ChoiceAnswer(first, 1.0, probs)
        return SystemOneResult(model="stub", answers=answers,
                               usage=Usage(10, 1), latency_s=0.0, raw={})


def _passport(pid, **kw):
    return Passport(id=pid, source="test", namespace="test",
                    kind=kw.pop("kind", "particle"),
                    ready_to_use=True, primitive=True, **kw)


def test_selector_two_stage_ordering():
    cands = [_passport(f"x:{i}") for i in range(40)] + [_passport("x:dust")]
    sel = EffectSelector(_StubClient(), batch_size=10, stage2_pool=5, top_k=3)
    res = sel.find_effects("anything", cands)
    assert res.stage1_evaluated == 41 and res.stage1_batches == 5
    # noul pushed x:dust into the finals even though it's alphabetically last
    assert "x:dust" in res.choice_distribution
    # final ranking follows stage-2 choice (stub picks alphabetically first)
    assert res.candidates[0].id == "x:0"
    assert res.candidates[0].choice_probability == 1.0
    assert len(res.candidates) == 3


def test_selector_missing_noul_marks_zero():
    class HalfClient(_StubClient):
        def system_one(self, state, questions, *, deadline_s=None):
            r = super().system_one(state, questions, deadline_s=deadline_s)
            r.answers.pop("c0", None)
            return r
    sel = EffectSelector(HalfClient(), batch_size=5, stage2_pool=2, top_k=2)
    res = sel.find_effects("q", [_passport(f"x:{i}") for i in range(5)])
    assert any("missing/invalid noul" in d for d in res.diagnostics)


# ------------------------------------------------------------- cache

def test_find_uses_query_cache(tmp_path, monkeypatch):
    # tiny catalog on disk
    cat = Catalog(resources={"x:dust": _passport("x:dust")})
    cat_path = tmp_path / "cat.json"
    cat.save(str(cat_path))

    import jevlab.find_effects as fe
    calls = {"n": 0}

    class CountingSelector:
        def __init__(self, *a, **k):
            self.inner = EffectSelector(_StubClient())

        def find_effects(self, q, cands):
            calls["n"] += 1
            return self.inner.find_effects(q, cands)

    monkeypatch.setattr(fe, "EffectSelector", CountingSelector)
    monkeypatch.setattr(fe, "TypeSafeClient", lambda *a, **k: object())

    r1, m1 = find("q", str(cat_path), cache_root=str(tmp_path / "cache"))
    r2, m2 = find("q", str(cat_path), cache_root=str(tmp_path / "cache"))
    assert m1["query_cache"] == "live" and m2["query_cache"] == "hit"
    assert calls["n"] == 1
    assert r1["candidates"] == r2["candidates"]

    r3, m3 = find("q", str(cat_path), cache_root=str(tmp_path / "cache"),
                  use_query_cache=False)
    assert m3["query_cache"] == "live" and calls["n"] == 2
